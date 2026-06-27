"""CLI Agent 桥接模块。

通过 subprocess 调用第三方 CLI agent（claude / opencode / codex / gemini），
将当前工作区作为 agent 的工作目录，流式回传输出。

对标 Tolaria 的 AiPanel + CLI agent 集成。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from config import config
from utils.logger import logger


# 登录 shell 环境缓存：GUI 启动时 PATH 不完整，通过登录 shell 获取用户真实环境
_login_shell_env: dict[str, str] | None = None
_login_shell_env_fetched = False


def _get_login_shell() -> str:
    """返回用户默认 shell，回退到 macOS 常见的 zsh/bash。"""
    shell = os.environ.get("SHELL", "").strip()
    if shell and Path(shell).exists():
        return shell
    for fallback in ("/bin/zsh", "/bin/bash"):
        if Path(fallback).exists():
            return fallback
    return "/bin/sh"


def _get_login_shell_env() -> dict[str, str]:
    """从登录 shell 获取用户环境变量（PATH、NVM、API key 等）。

    Tauri 侧载的 Python 子进程通常继承不到用户 shell 的完整环境，
    参考 cli-agents crate 的做法，通过登录 shell 读取 env。
    """
    global _login_shell_env, _login_shell_env_fetched
    if _login_shell_env_fetched:
        return _login_shell_env or {}

    _login_shell_env_fetched = True
    shell = _get_login_shell()
    try:
        proc = subprocess.run(
            [shell, "-l", "-c", "env"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            logger.warning(f"登录 shell env 获取失败: {proc.stderr.strip()}")
            return {}

        env: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            # 跳过 shell 内部变量，只保留有意义的导出变量
            if key and not key.startswith("_"):
                env[key] = value
        _login_shell_env = env
        logger.info("已从登录 shell 获取用户环境变量")
        return env
    except Exception as e:
        logger.warning(f"登录 shell env 获取异常: {e}")
        return {}


def _which_via_login_shell(cmd: str) -> str | None:
    """通过登录 shell 的 which 查找命令绝对路径。

    比 shutil.which 更可靠，能继承 shell rc 文件里的 PATH、nvm、fnm 等配置。
    """
    shell = _get_login_shell()
    try:
        proc = subprocess.run(
            [shell, "-l", "-c", f"command -v {cmd} || which {cmd}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return None
        path = proc.stdout.strip().splitlines()[0].strip()
        if path and Path(path).exists() and os.access(path, os.X_OK):
            return path
    except Exception as e:
        logger.debug(f"login shell which {cmd} 异常: {e}")
    return None


# 支持的 CLI agent 配置
# command: 主命令名（用于 shutil.which 与执行）
# command_aliases: 常见别名（用于检测）
# skip_permissions_args: 绕过交互式权限确认的 flag（参考 cli-agents crate）
SUPPORTED_AGENTS: dict[str, dict[str, Any]] = {
    "claude": {
        "command": "claude",
        "command_aliases": ["claude-code"],
        "args": ["-p", "{prompt}", "--include-directories", "{workspace}"],
        "skip_permissions_args": ["--dangerously-skip-permissions", "--no-session-persistence"],
        "env_keys": ["ANTHROPIC_API_KEY"],
        "display_name": "Claude Code",
        "description": "Anthropic Claude Code CLI",
    },
    "opencode": {
        "command": "opencode",
        "command_aliases": ["oc"],
        "args": ["run", "{prompt}"],
        "skip_permissions_args": [],
        "env_keys": ["OPENCODE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
        "display_name": "OpenCode",
        "description": "Open source terminal AI coding assistant",
    },
    "codex": {
        "command": "codex",
        "command_aliases": ["openai-codex"],
        "args": ["exec", "{prompt}"],
        "skip_permissions_args": ["--full-auto"],
        "env_keys": ["OPENAI_API_KEY"],
        "display_name": "Codex CLI",
        "description": "OpenAI Codex CLI",
    },
    "gemini": {
        "command": "gemini",
        "command_aliases": ["gemini-cli"],
        "args": ["-p", "{prompt}"],
        "skip_permissions_args": ["--mode", "autonomous"],
        "env_keys": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "display_name": "Gemini CLI",
        "description": "Google Gemini CLI",
    },
}

# 安全限制
MAX_PROMPT_LENGTH = 10000


def _validate_prompt(prompt: str) -> tuple[bool, str]:
    """校验用户 prompt，避免被外部 CLI 参数解析器误解释。"""
    if not prompt or not prompt.strip():
        return False, "prompt 不能为空"
    if len(prompt) > MAX_PROMPT_LENGTH:
        return False, f"prompt 超过最大长度 {MAX_PROMPT_LENGTH}"
    if "\x00" in prompt:
        return False, "prompt 包含非法空字符"
    # 控制字符仅允许常见空白，避免终端控制序列
    if any(ch != "\n" and ch != "\r" and ch != "\t" and ord(ch) < 32 for ch in prompt):
        return False, "prompt 包含非法控制字符"
    # 防止被解析为 CLI 选项（如 opencode run -foo）
    stripped = prompt.lstrip()
    if stripped.startswith("-"):
        return False, "prompt 不能以 '-' 开头"
    if stripped.startswith("-- "):
        return False, "prompt 不能以 '-- ' 开头"
    return True, ""


def _resolve_workspace(ws: str) -> tuple[Path | None, str]:
    """解析并校验工作区路径，返回 (path, error_message)。"""
    candidate = Path(ws).expanduser().resolve()
    if not candidate.exists():
        return None, f"工作区路径不存在: {ws}"
    if not candidate.is_dir():
        return None, f"工作区路径不是目录: {ws}"
    return candidate, ""


def _common_bin_dirs() -> list[Path]:
    """返回常见 CLI 安装目录。

    Tauri 侧载的 Python 子进程通常继承不到用户 shell 的完整 PATH，
    因此手动补充 Homebrew、npm 全局、bun、claude 本地安装等常见路径。
    """
    dirs: list[Path] = []
    home = Path.home()

    candidates = [
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
        "/bin",
        "/opt/homebrew/opt/node/bin",
        "/usr/local/opt/node/bin",
        home / ".local" / "bin",
        home / ".npm-global" / "bin",
        home / ".bun" / "bin",
        home / ".claude" / "local",
        home / ".nvm" / "versions" / "node",
    ]

    for c in candidates:
        if isinstance(c, str):
            p = Path(c)
        else:
            p = c
        if p.exists() and p.is_dir():
            # nvm 路径下面还有版本子目录
            if "nvm" in str(p) and (p / "..").name == "node":
                for sub in sorted(p.iterdir(), reverse=True):
                    if sub.is_dir():
                        bin_dir = sub / "bin"
                        if bin_dir.exists():
                            dirs.append(bin_dir)
            else:
                dirs.append(p)

    return dirs


def _resolve_command(cmd: str, aliases: list[str] | None = None) -> str | None:
    """在 PATH 与常见目录中解析命令，返回绝对路径或命令名。

    优先通过登录 shell 查找，继承用户 shell 的完整 PATH（nvm、homebrew 等）。
    """
    names = [cmd]
    if aliases:
        names.extend(aliases)

    # 1. 通过登录 shell 查找（最可靠，继承 .zshrc/.bashrc 的 PATH）
    for name in names:
        found = _which_via_login_shell(name)
        if found:
            return found

    # 2. 使用登录 shell 的 PATH 进行 shutil.which
    login_env = _get_login_shell_env()
    login_path = login_env.get("PATH", "")
    for name in names:
        found = shutil.which(name, path=login_path) if login_path else shutil.which(name)
        if found:
            return found

    # 3. 扫描常见安装目录
    for directory in _common_bin_dirs():
        for name in names:
            candidate = directory / name
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)

    return None


def list_available_agents() -> list[dict[str, Any]]:
    """列出所有支持的 agent 及其安装状态。"""
    agents = []
    for key, cfg in SUPPORTED_AGENTS.items():
        resolved = _resolve_command(cfg["command"], cfg.get("command_aliases", []))
        installed = resolved is not None
        agents.append({
            "id": key,
            "name": cfg["display_name"],
            "description": cfg["description"],
            "command": cfg["command"],
            "resolved_path": resolved,
            "installed": installed,
        })
    return agents


def _build_agent_env(cfg: dict[str, Any]) -> dict[str, str]:
    """合并当前环境变量、登录 shell 环境与 agent 所需的 API key。

    优先从 os.environ / config 读取，确保 GUI 启动时也能拿到 key。
    登录 shell 环境可补充 PATH、NVM、fnm 等配置。
    """
    login_env = _get_login_shell_env()
    # 优先级：当前进程 > 登录 shell > 默认值
    env = {**login_env, **os.environ, "NO_COLOR": "1", "FORCE_COLOR": "0"}
    for key in cfg.get("env_keys", []):
        val = os.environ.get(key)
        if not val and hasattr(config, key.lower()):
            val = getattr(config, key.lower())
        if not val:
            val = login_env.get(key)
        if val:
            env[key] = val
    return env


def run_cli_agent(
    agent_id: str,
    prompt: str,
    workspace_path: str | None = None,
    send_event=None,
    skip_permissions: bool = True,
):
    """启动 CLI agent 处理用户请求。

    参考 cli-agents crate 的做法：
    - 默认绕过交互式权限确认，避免 stdout 被 pipe 后卡在权限提示。
    - 设置 idle / total 超时，防止 agent 挂起。
    - 自动注入常见 API key。

    Args:
        agent_id: agent 标识符（claude / opencode / codex / gemini）
        prompt: 用户输入的提示词
        workspace_path: 工作区路径（默认使用 config.workspace_path）
        send_event: 流式事件回调函数
        skip_permissions: 是否跳过权限确认（默认 True）

    Returns:
        dict with success, message, output
    """
    if agent_id not in SUPPORTED_AGENTS:
        return {"success": False, "message": f"不支持的 agent: {agent_id}"}

    ok, msg = _validate_prompt(prompt)
    if not ok:
        return {"success": False, "message": msg}

    cfg = SUPPORTED_AGENTS[agent_id]
    command = _resolve_command(cfg["command"], cfg.get("command_aliases", []))

    # 检查是否安装
    if command is None:
        return {
            "success": False,
            "message": f"{cfg['display_name']} 未安装。请先安装 {cfg['command']} 命令行工具。",
        }

    ws = workspace_path or config.workspace_path
    if not ws:
        return {"success": False, "message": "未设置工作区"}

    ws_path, ws_err = _resolve_workspace(ws)
    if ws_path is None:
        return {"success": False, "message": ws_err}

    # 构建命令参数：每个占位符必须映射为独立的 argv 元素，禁止字符串拼接。
    try:
        args: list[str] = []
        if skip_permissions:
            args.extend(cfg.get("skip_permissions_args", []))
        for arg in cfg["args"]:
            if arg == "{prompt}":
                args.append(prompt)
            elif arg == "{workspace}":
                args.append(str(ws_path))
            elif "{prompt}" in arg or "{workspace}" in arg:
                # 拒绝模板内联拼接，防止参数注入
                return {"success": False, "message": "agent 配置包含不安全的参数模板"}
            else:
                args.append(arg)
    except Exception as e:
        return {"success": False, "message": f"参数构建失败: {e}"}

    full_cmd = [command] + args

    def _emit(payload: dict) -> None:
        if send_event:
            try:
                send_event(payload)
            except Exception:
                pass

    _emit({
        "type": "cli_agent_start",
        "agent": agent_id,
        "agent_name": cfg["display_name"],
        "command": command,
    })

    try:
        import subprocess
        import threading

        _emit({
            "type": "cli_agent_output",
            "agent": agent_id,
            "content": f"$ {' '.join(full_cmd)}\n",
        })

        env = _build_agent_env(cfg)

        # 启动子进程，工作目录设为工作区
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

        # 超时控制：idle 60s / total 5min
        idle_timeout_s = 60.0
        total_timeout_s = 300.0
        last_output_time = time.time()
        start_time = last_output_time
        killed = {"reason": None}

        def _check_timeout():
            nonlocal last_output_time
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

        output_lines: list[str] = []
        try:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                last_output_time = time.time()
                output_lines.append(line)
                _emit({
                    "type": "cli_agent_output",
                    "agent": agent_id,
                    "content": line,
                })
        finally:
            proc.stdout.close()
            try:
                return_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                return_code = proc.wait()

        output = "".join(output_lines)

        if killed["reason"]:
            _emit({
                "type": "cli_agent_error",
                "agent": agent_id,
                "message": killed["reason"],
                "output": output,
            })
            return {
                "success": False,
                "message": f"{cfg['display_name']} {killed['reason']}",
                "output": output,
            }

        if return_code != 0:
            _emit({
                "type": "cli_agent_error",
                "agent": agent_id,
                "message": f"{cfg['display_name']} 退出码: {return_code}",
            })
            return {
                "success": False,
                "message": f"{cfg['display_name']} 执行失败（退出码 {return_code}）",
                "output": output,
                "exit_code": return_code,
            }

        _emit({
            "type": "cli_agent_done",
            "agent": agent_id,
            "agent_name": cfg["display_name"],
            "output": output,
        })

        return {
            "success": True,
            "output": output,
            "exit_code": 0,
        }

    except FileNotFoundError:
        return {
            "success": False,
            "message": f"未找到 {command} 命令，请确认已安装并加入 PATH",
        }
    except Exception as e:
        logger.exception(f"CLI agent {agent_id} 执行异常")
        return {"success": False, "message": f"执行异常: {e}"}


# 别名修正（避免拼写错误）
