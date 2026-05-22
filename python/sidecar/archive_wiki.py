"""Archive RAG chat answers as Notes markdown (not wiki)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from config import config
from config.constants import NOTES_FOLDER
from utils.helpers import sanitize_filename
from utils.workspace_log import append_log

_SAVE_MARKER_RE = re.compile(r"\n?【存档建议】[：:]?\s*(是|否)\s*$", re.MULTILINE)


def parse_save_suggestion(text: str) -> tuple[str, bool]:
    """Strip 小忆 self-assessment marker; return (clean_answer, suggest_save)."""
    raw = (text or "").strip()
    if not raw:
        return "", False
    m = _SAVE_MARKER_RE.search(raw)
    if not m:
        return raw, False
    clean = _SAVE_MARKER_RE.sub("", raw).strip()
    return clean, m.group(1) == "是"


def archive_chat_answer(
    question: str,
    answer: str,
    topic: str = "",
    title: str = "",
) -> dict:
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}
    q = (question or "").strip()
    a, _ = parse_save_suggestion((answer or "").strip())
    if not q or not a:
        return {"success": False, "message": "问题或回答为空"}

    ws = Path(workspace)
    notes_dir = ws / NOTES_FOLDER / "小忆对话"
    notes_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    stem = sanitize_filename((title or q)[:60])
    filename = f"{date_str} {stem}.md"
    out_path = notes_dir / filename
    counter = 1
    while out_path.exists():
        out_path = notes_dir / f"{date_str} {stem}_{counter}.md"
        counter += 1

    topic_line = f'topic: "{topic.strip()}"\n' if topic.strip() else ""
    fm = (
        "---\n"
        f"{topic_line}"
        "source: xiaoyi_chat\n"
        f'archived_at: "{datetime.now().isoformat(timespec="seconds")}"\n'
        "---\n\n"
    )
    body = f"## 问题\n\n{q}\n\n## 回答\n\n{a}\n"
    out_path.write_text(fm + body, encoding="utf-8")
    rel = str(out_path.relative_to(ws))

    append_log("query", f"保存对话笔记: {out_path.name}", rel)

    return {"success": True, "path": rel, "message": f"已保存为笔记 {rel}"}
