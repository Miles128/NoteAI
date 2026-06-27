"""Google Gemini CLI agent。"""

from __future__ import annotations

from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent


class GeminiAgent(BaseCliAgent):
    agent_id = "gemini"
    display_name = "Gemini CLI"
    description = "Google Gemini CLI (MCP mode)"
    command = "gemini"
    aliases = ["gemini-cli"]
    env_keys = ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
    mcp_target = "gemini"

    def build_args(
        self,
        prompt: str,
        workspace: Path,
        skip_permissions: bool = True,
    ) -> list[str]:
        args: list[str] = []
        if skip_permissions:
            args.extend(["--mode", "autonomous"])
        args.extend(["-p", prompt])
        return args
