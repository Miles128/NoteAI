"""CLI Agent 桥接模块（兼容入口）。

具体实现已迁移到 sidecar/cli_agent/ 包，本文件保留旧版公开 API：
- list_available_agents()
- run_cli_agent()

以及部分旧版常量/工具函数的别名，避免现有调用方报错。
"""

from __future__ import annotations

from typing import Any

from sidecar.cli_agent import (
    list_available_agents as _list_available_agents,
    run_cli_agent as _run_cli_agent,
)
from sidecar.cli_agent.env import (
    build_agent_env as _build_agent_env,
    common_bin_dirs as _common_bin_dirs,
    get_login_shell as _get_login_shell,
    get_login_shell_env as _get_login_shell_env,
    merge_path as _merge_path,
    resolve_command as _resolve_command,
    resolve_workspace as _resolve_workspace,
    validate_prompt as _validate_prompt,
    which_via_login_shell as _which_via_login_shell,
)
from sidecar.cli_agent.registry import AgentRegistry, get_registry


# 旧版常量：最大 prompt 长度
MAX_PROMPT_LENGTH = 10000


def list_available_agents() -> list[dict[str, Any]]:
    """列出所有支持的 agent 及其安装状态。"""
    return _list_available_agents()


def run_cli_agent(
    agent_id: str,
    prompt: str,
    workspace_path: str | None = None,
    send_event: Any | None = None,
    skip_permissions: bool = True,
    *,
    new_session: bool = False,
) -> dict[str, Any]:
    """启动 CLI agent 处理用户请求。"""
    return _run_cli_agent(
        agent_id,
        prompt,
        workspace_path=workspace_path,
        send_event=send_event,
        skip_permissions=skip_permissions,
        new_session=new_session,
    )


# 旧版内部函数别名，保持向后兼容
_get_login_shell = _get_login_shell
_get_login_shell_env = _get_login_shell_env
_which_via_login_shell = _which_via_login_shell
_common_bin_dirs = _common_bin_dirs
_resolve_command = _resolve_command
_merge_path = _merge_path
_build_agent_env = _build_agent_env
_validate_prompt = _validate_prompt
_resolve_workspace = _resolve_workspace

# 旧版 SUPPORTED_AGENTS 字典：保留配置元数据，避免导入时触发 shell 查询
SUPPORTED_AGENTS: dict[str, dict[str, Any]] = {
    "claude": {
        "command": "claude",
        "display_name": "Claude Code",
        "description": "Anthropic Claude Code CLI (MCP mode)",
    },
    "opencode": {
        "command": "opencode",
        "display_name": "OpenCode",
        "description": "Open source terminal AI coding assistant",
    },
    "codex": {
        "command": "codex",
        "display_name": "Codex CLI",
        "description": "OpenAI Codex CLI",
    },
    "gemini": {
        "command": "gemini",
        "display_name": "Gemini CLI",
        "description": "Google Gemini CLI",
    },
    "kimi": {
        "command": "kimi",
        "display_name": "Kimi Code",
        "description": "Moonshot Kimi Code CLI",
    },
}


__all__ = [
    "AgentRegistry",
    "MAX_PROMPT_LENGTH",
    "SUPPORTED_AGENTS",
    "get_registry",
    "list_available_agents",
    "run_cli_agent",
]
