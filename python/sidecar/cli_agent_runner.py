"""CLI Agent 桥接模块。

通过 subprocess 调用第三方 CLI agent（claude / opencode / codex / gemini），
将当前工作区作为 agent 的工作目录，流式回传输出。

对标 Tolaria 的 AiPanel + CLI agent 集成。
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from typing import Any

from config import config
from utils.logger import logger


# 支持的 CLI agent 配置
SUPPORTED_AGENTS: dict[str, dict[str, Any]] = {
    "claude": {
        "command": "claude",
        "args": ["-p", "{prompt}", "--include-directories", "{workspace}"],
        "display_name": "Claude Code",
        "description": "Anthropic Claude Code CLI",
    },
    "opencode": {
        "command": "opencode",
        "args": ["run", "{prompt}"],
        "display_name": "OpenCode",
        "description": "Open source terminal AI coding assistant",
    },
    "codex": {
        "command": "codex",
        "args": ["--prompt", "{prompt}"],
        "display_name": "Codex CLI",
        "description": "OpenAI Codex CLI",
    },
    "gemini": {
        "command": "gemini",
        "args": ["-p", "{prompt}"],
        "display_name": "Gemini CLI",
        "description": "Google Gemini CLI",
    },
}


def list_available_agents() -> list[dict[str, Any]]:
    """列出所有支持的 agent 及其安装状态。"""
    agents = []
    for key, cfg in SUPPORTED_AGENTS.items():
        installed = shutil.which(cfg["command"]) is not None
        agents.append({
            "id": key,
            "name": cfg["display_name"],
            "description": cfg["description"],
            "command": cfg["command"],
            "installed": installed,
        })
    return agents


def run_cli_agent(
    agent_id: str,
    prompt: str,
    workspace_path: str | None = None,
    send_event=None,
) -> dict[str, Any]:
    """启动 CLI agent 处理用户请求。

    Args:
        agent_id: agent 标识符（claude / opencode / codex / gemini）
        prompt: 用户输入的提示词
        workspace_path: 工作区路径（默认使用 config.workspace_path）
        send_event: 流式事件回调函数

    Returns:
        dict with success, message, output
    """
    if agent_id not in SUPPORTED_AGENTS:
        return {"success": False, "message": f"不支持的 agent: {agent_id}"}

    cfg = SUPPORTED_AGENTS[agent_id]
    command = cfg["command"]

    # 检查是否安装
    if shutil.which(command) is None:
        return {
            "success": False,
            "message": f"{cfg['display_name']} 未安装。请先安装 {command} 命令行工具。",
        }

    ws = workspace_path or config.workspace_path
    if not ws:
        return {"success": False, "message": "未设置工作区"}

    ws_path = Path(ws).expanduser()
    if not ws_path.exists():
        return {"success": False, "message": f"工作区路径不存在: {ws}"}

    # 构建命令参数
    try:
        args = [arg.replace("{prompt}", prompt).replace("{workspace}", str(ws_path)) for arg in cfg["args"]]
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

        _emit({
            "type": "cli_agent_output",
            "agent": agent_id,
            "content": f"$ {command} (workspace: {ws_path.name})\n",
        })

        # 启动子进程，工作目录设为工作区
        proc = subprocess.Popen(
            full_cmd,
            cwd=str(ws_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "NO_COLOR": "1"},
        )

        output_lines: list[str] = []
        try:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                output_lines.append(line)
                _emit({
                    "type": "cli_agent_output",
                    "agent": agent_id,
                    "content": line,
                })
        finally:
            proc.stdout.close()
            return_code = proc.wait()

        output = "".join(output_lines)

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
