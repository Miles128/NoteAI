"""CLI agent 抽象基类与统一执行逻辑。"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from sidecar.cli_agent.env import (
    build_agent_env,
    resolve_command,
    resolve_workspace,
    validate_prompt,
)
from sidecar.cli_agent.process_control import CliProcessHandle, TimeoutWatcher, clear, register
from sidecar.cli_agent.workspace_bounds import (
    append_workspace_boundary,
    apply_workspace_bounds_env,
    boundary_block,
)
from sidecar.mcp_config_manager import get_mcp_config_path, register_mcp_server
from utils.logger import logger


EventEmitter = Callable[[dict[str, Any]], None]


class AgentResult:
    """CLI agent 执行结果。"""

    def __init__(
        self,
        success: bool,
        message: str = "",
        output: str = "",
        exit_code: int | None = None,
    ):
        self.success = success
        self.message = message
        self.output = output
        self.exit_code = exit_code

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": self.success,
            "message": self.message,
            "output": self.output,
        }
        if self.exit_code is not None:
            result["exit_code"] = self.exit_code
        return result


class BaseCliAgent(ABC):
    """CLI agent 抽象基类。

    每个第三方 CLI agent（claude / opencode / codex / gemini / kimi 等）
    继承此类，只需覆盖命令参数构建与元数据。
    """

    agent_id: str = ""
    display_name: str = ""
    description: str = ""
    command: str = ""
    aliases: list[str] | None = None
    env_keys: list[str] | None = None
    # 非空时在 run() 前自动注册 NoteAI vault MCP server
    mcp_target: str | None = None
    # 是否支持 CLI 原生 session/continue（不支持则每次独立 run）
    supports_cli_session: bool = True

    # 默认超时：idle 180s / total 5min
    idle_timeout_s: float = 180.0
    total_timeout_s: float = 300.0

    def __init__(self) -> None:
        self.aliases = self.aliases or []
        self.env_keys = self.env_keys or []

    @property
    def resolved_path(self) -> str | None:
        """缓存解析出的可执行文件路径。"""
        return resolve_command(self.command, self.aliases)

    def is_installed(self) -> bool:
        """该 agent 是否已安装可用。"""
        return self.resolved_path is not None

    def check_api_keys(self) -> list[str]:
        """返回当前可用的 API key 名称列表。"""
        from sidecar.cli_agent.env import get_login_shell_env, lookup_api_key

        login_env = get_login_shell_env()
        return [key for key in self.env_keys if lookup_api_key(key, login_env)]

    def has_api_key(self) -> bool:
        """是否至少有一个可用的 API key。"""
        if not self.env_keys:
            return True
        return bool(self.check_api_keys())

    def info(self) -> dict[str, Any]:
        """返回 agent 基本信息与安装状态。"""
        return {
            "id": self.agent_id,
            "name": self.display_name,
            "description": self.description,
            "command": self.command,
            "resolved_path": self.resolved_path,
            "installed": self.is_installed(),
        }

    @abstractmethod
    def build_args(
        self,
        prompt: str,
        workspace: Path,
        skip_permissions: bool = True,
        *,
        continue_session: bool = False,
    ) -> list[str]:
        """构建传给 CLI 的参数列表（不含命令本身）。"""

    def build_env(self) -> dict[str, str]:
        """构建子进程环境变量。"""
        return build_agent_env(self.env_keys)

    def _validate_and_prepare(
        self,
        prompt: str,
        workspace_path: str | None,
    ) -> tuple[Path | None, AgentResult | None]:
        """校验 prompt 与工作区，返回 (workspace, error_result)。"""
        ok, msg = validate_prompt(prompt)
        if not ok:
            return None, AgentResult(False, msg)

        from config import config

        ws = workspace_path or config.workspace_path
        ws_path, ws_err = resolve_workspace(ws)
        if ws_path is None:
            return None, AgentResult(False, ws_err)
        return ws_path, None

    def _emit(self, event: dict[str, Any], send_event: EventEmitter | None) -> None:
        if send_event is None:
            return
        try:
            send_event(event)
        except Exception:
            pass

    def _ensure_mcp_registered(self, workspace: Path) -> str | None:
        """启动前注册 NoteAI vault MCP；失败时返回错误信息。"""
        if not self.mcp_target:
            return None
        result = register_mcp_server(
            targets=[self.mcp_target],
            workspace_path=str(workspace),
        )
        registered = result.get("registered") or []
        if registered:
            return None
        errors = result.get("errors") or []
        if errors:
            return f"MCP 配置注册失败: {errors[0]}"
        return None

    def run(
        self,
        prompt: str,
        workspace_path: str | None = None,
        send_event: EventEmitter | None = None,
        skip_permissions: bool = True,
        *,
        new_session: bool = False,
    ) -> AgentResult:
        """统一执行入口：解析命令、校验、启动子进程、流式输出、超时控制。"""
        from sidecar.cli_agent.session_store import (
            clear_session,
            has_session,
            mark_session,
        )

        command = self.resolved_path
        logger.info(f"CLI agent {self.agent_id} 解析命令: {command}")

        if command is None:
            logger.warning(f"CLI agent {self.agent_id} 未找到可执行文件")
            return AgentResult(
                False,
                f"{self.display_name} 未安装。请先安装 {self.command} 命令行工具。",
            )

        if not self.has_api_key():
            return AgentResult(
                False,
                f"{self.display_name} 需要至少一个 API key: {', '.join(self.env_keys)}。"
                "请在环境变量或 shell 配置中设置。",
            )

        ws_path, error = self._validate_and_prepare(prompt, workspace_path)
        if error:
            return error
        assert ws_path is not None
        ws_key = str(ws_path)

        if new_session and self.supports_cli_session:
            clear_session(self.agent_id, ws_key)

        continue_session = (
            self.supports_cli_session and has_session(self.agent_id, ws_key)
        )

        mcp_error = self._ensure_mcp_registered(ws_path)
        if mcp_error:
            return AgentResult(False, mcp_error)

        try:
            args = self.build_args(
                prompt,
                ws_path,
                skip_permissions,
                continue_session=continue_session,
            )
        except ValueError as e:
            return AgentResult(False, f"参数构建失败: {e}")

        full_cmd = [command] + args
        logger.info(
            f"CLI agent {self.agent_id} 启动命令: {' '.join(full_cmd)} "
            f"(cwd={ws_path}, continue={continue_session})"
        )

        self._emit(
            {
                "type": "cli_agent_start",
                "agent": self.agent_id,
                "agent_name": self.display_name,
                "command": command,
                "continue_session": continue_session,
            },
            send_event,
        )

        try:
            env = build_agent_env(self.env_keys)
            env = apply_workspace_bounds_env(env, self.agent_id, ws_path)
            proc = subprocess.Popen(
                full_cmd,
                cwd=str(ws_path),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            handle = register(proc, self.agent_id, self.display_name)
            try:
                killed = self._stream_output(proc, send_event, handle)
            finally:
                clear(handle)
            output = killed.get("output", "")

            if killed["reason"]:
                logger.warning(f"CLI agent {self.agent_id} 终止: {killed['reason']}")
                stopped = killed["reason"] == "用户已停止"
                self._emit(
                    {
                        "type": "cli_agent_error",
                        "agent": self.agent_id,
                        "message": killed["reason"],
                        "output": output,
                        "stopped_by_user": stopped,
                    },
                    send_event,
                )
                return AgentResult(
                    False,
                    f"{self.display_name} {killed['reason']}",
                    output,
                )

            return_code = proc.returncode
            if return_code != 0:
                logger.warning(
                    f"CLI agent {self.agent_id} 非零退出 ({return_code}): {output[:500]}"
                )
                if self.supports_cli_session:
                    clear_session(self.agent_id, ws_key)
                self._emit(
                    {
                        "type": "cli_agent_error",
                        "agent": self.agent_id,
                        "message": f"{self.display_name} 退出码: {return_code}",
                    },
                    send_event,
                )
                return AgentResult(
                    False,
                    f"{self.display_name} 执行失败（退出码 {return_code}）",
                    output,
                    return_code,
                )

            if self.supports_cli_session:
                mark_session(self.agent_id, ws_key)

            self._emit(
                {
                    "type": "cli_agent_done",
                    "agent": self.agent_id,
                    "agent_name": self.display_name,
                    "output": output,
                    "continue_session": True,
                },
                send_event,
            )
            return AgentResult(True, output=output, exit_code=0)

        except FileNotFoundError:
            return AgentResult(
                False,
                f"未找到 {command} 命令，请确认已安装并加入 PATH",
            )
        except Exception as e:
            logger.exception(f"CLI agent {self.agent_id} 执行异常")
            return AgentResult(False, f"执行异常: {e}")

    def _stream_output(
        self,
        proc: subprocess.Popen[str],
        send_event: EventEmitter | None,
        handle: CliProcessHandle,
    ) -> dict[str, Any]:
        """读取子进程输出并发送事件，返回 {reason, output}。"""
        killed: dict[str, Any] = {"reason": None, "output": ""}
        output_lines: list[str] = []

        watcher = TimeoutWatcher(
            handle,
            self.idle_timeout_s,
            self.total_timeout_s,
            lambda event: self._emit(event, send_event),
        )
        watcher.start()

        try:
            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                watcher.note_output()
                output_lines.append(line)
                self._emit(
                    {
                        "type": "cli_agent_output",
                        "agent": self.agent_id,
                        "content": line,
                    },
                    send_event,
                )
        finally:
            proc.stdout.close()  # type: ignore[union-attr]
            try:
                return_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                return_code = proc.wait()

            if watcher.kill_reason:
                killed["reason"] = watcher.kill_reason
            elif handle.stop_event.is_set():
                killed["reason"] = "用户已停止"
            elif return_code != 0 and killed["reason"] is None:
                pass

        killed["output"] = "".join(output_lines)
        return killed
