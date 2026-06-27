"""OpenCode CLI agent。"""

from __future__ import annotations

from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent


class OpenCodeAgent(BaseCliAgent):
    agent_id = "opencode"
    display_name = "OpenCode"
    description = "Open source terminal AI coding assistant (MCP mode)"
    command = "opencode"
    aliases = ["oc"]
    env_keys = ["OPENCODE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    mcp_target = "opencode"

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
