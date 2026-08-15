"""Kimi Code CLI agent。

Kimi Code 是 Moonshot AI 推出的终端 AI 编程助手，命令通常为 kimi。
启动前自动注册 ~/.kimi-code/mcp.json 中的 NoteAI vault MCP server。
"""

from __future__ import annotations

import os
from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent
from sidecar.cli_agent.workspace_bounds import append_workspace_boundary


class KimiAgent(BaseCliAgent):
    agent_id = "kimi"
    display_name = "Kimi Code"
    description = "Moonshot Kimi Code CLI (MCP mode)"
    command = "kimi"
    aliases = ["kimi-code"]
    env_keys = ["MOONSHOT_API_KEY", "KIMI_API_KEY"]
    mcp_target = "kimi"

    @classmethod
    def _saved_auth_exists(cls) -> bool:
        """Kimi 已登录凭据（oauth）是否已保存。

        kimi 自己维护登录态（`kimi auth login`），凭据存于
        ~/.kimi-code/credentials/，无需环境变量。
        """
        candidates = [
            Path.home() / ".kimi-code" / "credentials" / "kimi-code.json",
            Path.home() / ".kimi-code" / "credentials",
        ]
        if os.name == "nt":
            candidates.insert(0, Path(os.environ.get("USERPROFILE", "")) / ".kimi-code" / "credentials")
        return any(p.is_file() for p in candidates if p.is_file() or p.exists())

    def has_api_key(self) -> bool:
        """环境变量 key 或 kimi 已保存的登录凭据，满足其一即可。"""
        if super().has_api_key():
            return True
        return self._saved_auth_exists()

    def build_args(
        self,
        prompt: str,
        workspace: Path,
        skip_permissions: bool = True,
        *,
        continue_session: bool = False,
        model: str | None = None,
        variant: str | None = None,
    ) -> list[str]:
        args: list[str] = []
        if continue_session:
            args.append("-C")
        if skip_permissions:
            args.append("-y")
        scoped = append_workspace_boundary(
            prompt,
            workspace,
            continue_session=continue_session,
        )
        args.extend(["-p", scoped])
        return args
