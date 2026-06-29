"""OpenAI Codex CLI agent。"""

from __future__ import annotations

from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent
from sidecar.cli_agent.workspace_bounds import append_workspace_boundary


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
        *,
        continue_session: bool = False,
    ) -> list[str]:
        scoped_prompt = append_workspace_boundary(
            prompt,
            workspace,
            continue_session=continue_session,
        )
        common = ["exec", "--sandbox", "workspace-write", "-C", str(workspace)]
        if continue_session:
            return common + ["resume", "--last", scoped_prompt]
        return common + [scoped_prompt]
