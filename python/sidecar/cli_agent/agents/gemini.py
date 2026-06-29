"""Google Gemini CLI agent。"""

from __future__ import annotations

from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent
from sidecar.cli_agent.workspace_bounds import append_workspace_boundary


class GeminiAgent(BaseCliAgent):
    agent_id = "gemini"
    display_name = "Gemini CLI"
    description = "Google Gemini CLI (MCP mode)"
    command = "gemini"
    aliases = ["gemini-cli"]
    env_keys = ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
    mcp_target = "gemini"
    supports_cli_session = False

    def build_args(
        self,
        prompt: str,
        workspace: Path,
        skip_permissions: bool = True,
        *,
        continue_session: bool = False,
    ) -> list[str]:
        args: list[str] = []
        if skip_permissions:
            args.extend(["--mode", "autonomous"])
        scoped = append_workspace_boundary(
            prompt,
            workspace,
            continue_session=continue_session,
        )
        args.extend(["-p", scoped])
        return args
