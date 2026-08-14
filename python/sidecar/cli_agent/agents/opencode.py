"""OpenCode CLI agent。"""

from __future__ import annotations

import os
from pathlib import Path

from sidecar.cli_agent.base import BaseCliAgent
from sidecar.cli_agent.workspace_bounds import append_workspace_boundary, boundary_block


class OpenCodeAgent(BaseCliAgent):
    agent_id = "opencode"
    display_name = "OpenCode"
    description = "Open source terminal AI coding assistant (MCP mode)"
    command = "opencode"
    aliases = ["oc"]
    env_keys = ["OPENCODE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
    mcp_target = "opencode"

    @classmethod
    def _saved_auth_exists(cls) -> bool:
        """OpenCode 已登录凭据（auth.json）是否已保存。

        opencode 自己维护登录态（`opencode auth login`），凭据存于
        XDG data dir 下的 auth.json，无需环境变量。
        """
        candidates = []
        xdg = os.environ.get("XDG_DATA_HOME", "").strip()
        if xdg:
            candidates.append(Path(xdg) / "opencode" / "auth.json")
        candidates.append(Path.home() / ".local" / "share" / "opencode" / "auth.json")
        candidates.append(Path.home() / "Library" / "Application Support" / "opencode" / "auth.json")
        return any(p.is_file() for p in candidates)

    def has_api_key(self) -> bool:
        """环境变量 key 或 opencode 已保存的登录凭据，满足其一即可。"""
        if super().has_api_key():
            return True
        return self._saved_auth_exists()

    @staticmethod
    def enrich_prompt(prompt: str, workspace: Path) -> str:
        """为 OpenCode 注入工作区上下文，避免在错误目录搜索笔记。"""
        notes = workspace / "Notes"
        wiki = workspace / "wiki"
        raw = workspace / "Raw"
        return (
            "[NoteAI 工作区上下文]\n"
            f"- 工作区根目录: {workspace}\n"
            f"- 笔记目录: {notes}（所有 Markdown 笔记在此；不在 NoteAI 源码项目目录）\n"
            f"- 结构化知识: {wiki}\n"
            f"- 原始归档: {raw}\n"
            "- 访问笔记优先使用 noteai-vault MCP（vault_list_topics / vault_list_notes / "
            "vault_read_note / vault_search_notes）\n"
            "- vault 路径相对工作区根目录，例如 Notes/AI产品经理之路/01_认知重塑/术语手册.md\n"
            "- 当前 cwd 已是工作区根目录；中文主题文件夹通常无空格（如 AI产品经理之路）\n"
            "- 批量分析请分批读取，避免一次启动过多子 Agent\n"
            f"{boundary_block(workspace)}\n"
            "\n"
            "[用户任务]\n"
            f"{prompt.strip()}\n"
        )

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
        args: list[str] = ["run", "--dir", str(workspace)]
        if skip_permissions:
            args.append("--dangerously-skip-permissions")
        if model:
            args += ["-m", model]
        if variant:
            args += ["--variant", variant]
        if continue_session:
            args.append("-c")
        body = prompt.strip()
        if not continue_session:
            body = self.enrich_prompt(prompt, workspace)
        else:
            body = append_workspace_boundary(prompt, workspace, continue_session=True)
        args.append(body)
        return args
