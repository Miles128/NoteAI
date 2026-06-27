"""Kimi Code CLI agent。

Kimi Code 是 Moonshot AI 推出的终端 AI 编程助手，命令通常为 kimi。
启动前自动注册 ~/.kimi-code/mcp.json 中的 NoteAI vault MCP server。
"""

from __future__ import annotations

from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent


class KimiAgent(BaseCliAgent):
    agent_id = "kimi"
    display_name = "Kimi Code"
    description = "Moonshot Kimi Code CLI (MCP mode)"
    command = "kimi"
    aliases = ["kimi-code"]
    env_keys = ["MOONSHOT_API_KEY", "KIMI_API_KEY"]
    mcp_target = "kimi"

    def build_args(
        self,
        prompt: str,
        workspace: Path,
        skip_permissions: bool = True,
    ) -> list[str]:
        args: list[str] = ["run"]
        if skip_permissions:
            args.append("--dangerously-skip-permissions")
        args.append(prompt)
        return args
