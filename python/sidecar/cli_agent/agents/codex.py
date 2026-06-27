"""OpenAI Codex CLI agent。"""

from __future__ import annotations

from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent


class CodexAgent(BaseCliAgent):
    agent_id = "codex"
    display_name = "Codex CLI"
    description = "OpenAI Codex CLI (MCP mode)"
    command = "codex"
    aliases = ["openai-codex"]
    env_keys = ["OPENAI_API_KEY"]
    mcp_target = "codex"

    def build_args(
        self,
        prompt: str,
        workspace: Path,
        skip_permissions: bool = True,
    ) -> list[str]:
        # 注意：--full-auto 必须放在 exec 之后
        return ["exec", "--full-auto", prompt]
