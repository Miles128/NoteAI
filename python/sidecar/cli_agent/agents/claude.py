"""Claude Code CLI agent。"""

from __future__ import annotations

from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent


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
    ) -> list[str]:
        args: list[str] = []
        if skip_permissions:
            args.extend(["--dangerously-skip-permissions", "--no-session-persistence"])
        args.extend(["-p", prompt, "--add-dir", str(workspace)])
        return args
