"""CLI agent 工作区边界：限制读写范围在当前 vault 内。"""

from __future__ import annotations

import json
from pathlib import Path

WORKSPACE_BOUNDARY_HEADER = "[工作区安全边界 — 必须遵守]"

WORKSPACE_BOUNDARY_TEMPLATE = """\
{header}
- 你只能读取、创建、修改、删除当前工作区目录内的文件
- 工作区根目录: {workspace}
- 禁止访问或修改工作区外的任何路径（包括用户主目录、/tmp、NoteAI 源码、其他项目）
- shell / bash 命令的工作目录必须在工作区内；不要使用 cd 跳出工作区
- 若任务必须涉及工作区外路径，请向用户说明并停止，不要尝试操作
"""

WORKSPACE_BOUNDARY_REMINDER = "[提醒] 所有文件操作仅限工作区: {workspace}"


def boundary_block(workspace: Path) -> str:
    return WORKSPACE_BOUNDARY_TEMPLATE.format(
        header=WORKSPACE_BOUNDARY_HEADER,
        workspace=workspace,
    ).strip()


def append_workspace_boundary(
    prompt: str,
    workspace: Path,
    *,
    continue_session: bool = False,
) -> str:
    """在 prompt 前注入工作区边界说明。"""
    body = (prompt or "").strip()
    if continue_session:
        reminder = WORKSPACE_BOUNDARY_REMINDER.format(workspace=workspace)
        return f"{body}\n\n{reminder}"
    return f"{boundary_block(workspace)}\n\n{body}"


# OpenCode: external_directory=deny 阻止工作区外路径（deny 优先于 skip-permissions）
OPENCODE_BOUNDS_CONFIG: dict = {
    "permission": {
        "external_directory": "deny",
    },
}


def apply_workspace_bounds_env(
    env: dict[str, str],
    agent_id: str,
    workspace: Path,
) -> dict[str, str]:
    """为各 CLI 注入运行时工作区限制环境变量。"""
    merged = dict(env)
    if agent_id == "opencode":
        merged["OPENCODE_CONFIG_CONTENT"] = json.dumps(
            OPENCODE_BOUNDS_CONFIG,
            ensure_ascii=False,
        )
    return merged
