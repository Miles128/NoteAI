"""Claude Code CLI agent。"""

from __future__ import annotations

from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent
from sidecar.cli_agent.workspace_bounds import append_workspace_boundary


class ClaudeAgent(BaseCliAgent):
    agent_id = "claude-legacy"
    display_name = "Claude Code (Legacy)"
    description = "Anthropic Claude Code CLI (direct mode)"
    command = "claude"
    aliases = ["claude-code"]
    env_keys = ["ANTHROPIC_API_KEY"]

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
            args.extend(["--permission-mode", "acceptEdits"])
        if continue_session:
            args.append("-c")
        scoped = append_workspace_boundary(
            prompt,
            workspace,
            continue_session=continue_session,
        )
        args.extend(["-p", scoped, "--add-dir", str(workspace)])
        return args
