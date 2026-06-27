"""Claude Code MCP agent — 直接 spawn Claude CLI 并利用其内置 tool loop。"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from sidecar.cli_agent.base import AgentResult, BaseCliAgent, EventEmitter
from sidecar.cli_agent.env import build_agent_env, resolve_command
from sidecar.cli_agent.tool_events import (
    ToolStreamTracker,
    emit_tool_events,
    tool_results_from_message,
    tool_uses_from_message,
)
from sidecar.mcp_config_manager import get_mcp_config_path, register_mcp_server
from utils.logger import logger


class ClaudeMcpAgent(BaseCliAgent):
    """通过 Claude CLI 的 --mcp-config 启动，利用其内置 NDJSON tool loop。

    对标 Tolaria 的 claude_cli.rs + useAiAgent：Claude CLI 自己处理 MCP 工具、
    对话历史和调用循环，NoteAI 只需解析事件流并渲染。
    """

    agent_id = "claude"
    display_name = "Claude Code"
    description = "Anthropic Claude Code CLI (MCP mode)"
    command = "claude"
    aliases = ["claude-code"]
    env_keys = ["ANTHROPIC_API_KEY"]
    mcp_target = "claude"

    def build_args(
        self,
        prompt: str,
        workspace: Path,
        skip_permissions: bool = True,
    ) -> list[str]:
        # 由 run() 直接构造完整命令，这里只返回最简参数
        return ["-p", prompt]

    def _ensure_mcp_config(self, workspace: Path) -> Path | None:
        """确保 Claude 的 MCP 配置已注册，返回配置文件路径。"""
        result = register_mcp_server(targets=["claude"], workspace_path=str(workspace))
        if "claude" not in (result.get("registered") or []):
            return None
        return get_mcp_config_path("claude")

    def run(
        self,
        prompt: str,
        workspace_path: str | None = None,
        send_event: EventEmitter | None = None,
        skip_permissions: bool = True,
    ) -> AgentResult:
        command = self.resolved_path
        if command is None:
            return AgentResult(
                False,
                f"{self.display_name} 未安装。请先安装 {self.command} 命令行工具。",
            )

        from sidecar.cli_agent.env import resolve_workspace, validate_prompt

        ok, msg = validate_prompt(prompt)
        if not ok:
            return AgentResult(False, msg)

        from config import config

        ws = workspace_path or config.workspace_path
        ws_path, ws_err = resolve_workspace(ws)
        if ws_path is None:
            return AgentResult(False, ws_err)

        mcp_config_path = self._ensure_mcp_config(ws_path)
        if mcp_config_path is None or not mcp_config_path.exists():
            return AgentResult(False, "MCP 配置生成失败")

        args = [
            "--output-format", "stream-json",
            "--verbose",
            "--mcp-config", str(mcp_config_path),
            "-p", prompt,
        ]
        if skip_permissions:
            args.extend(["--dangerously-skip-permissions", "--no-session-persistence"])

        full_cmd = [command] + args
        logger.info(
            f"Claude MCP agent 启动命令: {' '.join(full_cmd)} (cwd={ws_path})"
        )

        self._emit(
            {
                "type": "cli_agent_start",
                "agent": self.agent_id,
                "agent_name": self.display_name,
                "command": command,
            },
            send_event,
        )

        try:
            env = build_agent_env(self.env_keys)
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

            return self._stream_ndjson(proc, send_event)

        except FileNotFoundError:
            return AgentResult(False, f"未找到 {command} 命令")
        except Exception as e:
            logger.exception("Claude MCP agent 执行异常")
            return AgentResult(False, f"执行异常: {e}")

    def _emit(self, event: dict[str, Any], send_event: EventEmitter | None) -> None:
        if send_event is None:
            return
        try:
            send_event(event)
        except Exception:
            pass

    def _stream_ndjson(
        self,
        proc: subprocess.Popen[str],
        send_event: EventEmitter | None,
    ) -> AgentResult:
        """解析 Claude CLI 的 NDJSON 流并转换为现有 CLI agent 事件。"""
        idle_timeout_s = self.idle_timeout_s
        total_timeout_s = self.total_timeout_s
        last_output_time = time.time()
        start_time = last_output_time
        killed = {"reason": None}
        output_lines: list[str] = []
        text_buffer = ""
        tool_tracker = ToolStreamTracker()
        tool_context: dict[str, dict[str, Any]] = {}

        def _check_timeout() -> None:
            while proc.poll() is None:
                now = time.time()
                if now - last_output_time > idle_timeout_s:
                    killed["reason"] = f"idle 超过 {int(idle_timeout_s)}s 无输出"
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return
                if now - start_time > total_timeout_s:
                    killed["reason"] = f"总运行时间超过 {int(total_timeout_s)}s"
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return
                time.sleep(1.0)

        timeout_thread = threading.Thread(target=_check_timeout, daemon=True)
        timeout_thread.start()

        try:
            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                last_output_time = time.time()
                output_lines.append(line)

                event = self._parse_ndjson_line(line)
                if event:
                    chunk = self._forward_event(
                        event,
                        send_event,
                        tool_tracker,
                        tool_context,
                    )
                    if chunk:
                        text_buffer += chunk
        finally:
            proc.stdout.close()  # type: ignore[union-attr]
            try:
                return_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                return_code = proc.wait()

        output = "".join(output_lines)

        if killed["reason"]:
            self._emit(
                {
                    "type": "cli_agent_error",
                    "agent": self.agent_id,
                    "message": killed["reason"],
                    "output": output,
                },
                send_event,
            )
            return AgentResult(False, f"{self.display_name} {killed['reason']}", output)

        self._emit(
            {
                "type": "cli_agent_done",
                "agent": self.agent_id,
                "agent_name": self.display_name,
                "output": text_buffer or output,
            },
            send_event,
        )
        return AgentResult(True, output=text_buffer or output, exit_code=return_code)

    def _parse_ndjson_line(self, line: str) -> dict[str, Any] | None:
        """解析 Claude CLI 的 NDJSON 行。"""
        line = line.strip()
        if not line:
            return None
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict) and parsed.get("type") == "system":
                return None
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            stripped = line.strip()
            if stripped.startswith("{") and '"type"' in stripped:
                return None
            if stripped.startswith("Ignoring --") or stripped.startswith("Error:"):
                return None
            return {"type": "text", "text": line + "\n"}

    def _extract_assistant_text(self, event: dict[str, Any]) -> str:
        """从 Claude NDJSON 事件提取应展示给用户的文本。"""
        etype = event.get("type")
        if etype == "text":
            return str(event.get("text", ""))
        if etype == "TextDelta":
            return str(event.get("delta", ""))
        if etype == "stream_event":
            inner = event.get("event") or {}
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta") or {}
                if delta.get("type") == "text_delta":
                    return str(delta.get("text", ""))
            return ""
        if etype == "assistant":
            message = event.get("message") or {}
            parts: list[str] = []
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            return "".join(parts)
        if etype == "result":
            return str(event.get("result", "") or "")
        return ""

    def _forward_event(
        self,
        event: dict[str, Any],
        send_event: EventEmitter | None,
        tool_tracker: ToolStreamTracker,
        tool_context: dict[str, dict[str, Any]],
    ) -> str:
        """把 Claude CLI 事件转成 panel 输出；返回应追加的 assistant 文本。"""
        etype = event.get("type")

        if etype == "user":
            message = event.get("message") or {}
            for payload in tool_results_from_message(message):
                tool_id = payload.get("tool_id") or ""
                ctx = tool_tracker.lookup(tool_id) or tool_context.get(tool_id) or {}
                payload["tool"] = payload.get("tool") or ctx.get("tool")
                payload["input"] = ctx.get("input") or {}
                emit_tool_events(self.agent_id, [payload], send_event, self._emit)
            return ""

        if etype == "assistant":
            message = event.get("message") or {}
            for payload in tool_uses_from_message(message):
                tool_id = payload.get("tool_id") or ""
                if tool_id:
                    tool_context[tool_id] = {
                        "tool": payload.get("tool"),
                        "input": payload.get("input") or {},
                    }
                emit_tool_events(self.agent_id, [payload], send_event, self._emit)

        if etype == "stream_event":
            inner = event.get("event") or {}
            for payload in tool_tracker.handle_stream_event(inner):
                tool_id = payload.get("tool_id") or ""
                if tool_id:
                    tool_context[tool_id] = {
                        "tool": payload.get("tool"),
                        "input": payload.get("input") or {},
                    }
                emit_tool_events(self.agent_id, [payload], send_event, self._emit)

        if etype in ("system", "ThinkingDelta", "ToolStart", "ToolDone", "Result", "Done"):
            if etype == "ToolStart":
                tool = event.get("tool") or {}
                payload = {
                    "phase": "start",
                    "tool_id": str(tool.get("id") or tool.get("name") or ""),
                    "tool": str(tool.get("name") or "tool"),
                    "input": tool.get("input") if isinstance(tool.get("input"), dict) else {},
                }
                emit_tool_events(self.agent_id, [payload], send_event, self._emit)
            elif etype == "ToolDone":
                tool = event.get("tool") or {}
                payload = {
                    "phase": "done",
                    "tool_id": str(tool.get("id") or tool.get("name") or ""),
                    "tool": str(tool.get("name") or "tool"),
                    "success": not bool(event.get("error")),
                    "result": str(event.get("result") or "")[:2000],
                }
                emit_tool_events(self.agent_id, [payload], send_event, self._emit)
            return ""

        if etype == "Error":
            self._emit(
                {
                    "type": "cli_agent_error",
                    "agent": self.agent_id,
                    "message": event.get("error", "Claude CLI 错误"),
                },
                send_event,
            )
            return ""

        text = self._extract_assistant_text(event)
        if not text:
            return ""
        self._emit(
            {
                "type": "cli_agent_output",
                "agent": self.agent_id,
                "content": text,
            },
            send_event,
        )
        return text
