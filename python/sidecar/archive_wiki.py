"""Archive RAG chat answers as Notes or wiki markdown."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from config import config
from config.constants import NOTES_FOLDER
from config.settings import ABSTRACT_FOLDER
from sidecar.schema_validator import check_notes_writable, check_wiki_writable, require_topic
from utils.helpers import sanitize_filename
from utils.wiki_manager import topic_from_notes_path
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


def _resolve_topic(topic: str, context_file: str, ws: Path) -> str:
    t = (topic or "").strip()
    if t:
        return t
    ctx = (context_file or "").strip()
    if not ctx:
        return ""
    path = Path(ctx)
    if not path.is_absolute():
        path = ws / ctx
    if path.exists():
        derived = topic_from_notes_path(path)
        if derived:
            return derived
    return ""


def archive_chat_answer(
    question: str,
    answer: str,
    topic: str = "",
    title: str = "",
    target: str = "note",
    context_file: str = "",
) -> dict:
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}
    q = (question or "").strip()
    a, _ = parse_save_suggestion((answer or "").strip())
    if not q or not a:
        return {"success": False, "message": "问题或回答为空"}

    ws = Path(workspace)
    resolved_topic = _resolve_topic(topic, context_file, ws)
    date_str = datetime.now().strftime("%Y-%m-%d")
    stem = sanitize_filename((title or q)[:60])
    filename = f"{date_str} {stem}.md"

    save_target = (target or "note").strip().lower()
    if save_target == "wiki":
        ok, err = check_wiki_writable("保存对话到 wiki")
        if not ok:
            return {"success": False, "message": err}
        out_dir = ws / ABSTRACT_FOLDER / "小忆对话"
        log_action = "query_wiki"
        log_prefix = "保存对话到 wiki"
        success_hint = f"已保存到 {ABSTRACT_FOLDER}/小忆对话/"
    else:
        ok, err = check_notes_writable("保存对话笔记")
        if not ok:
            return {"success": False, "message": err}
        out_dir = ws / NOTES_FOLDER / "小忆对话"
        log_action = "query"
        log_prefix = "保存对话笔记"
        success_hint = "已保存到 Notes/小忆对话/"

    if resolved_topic:
        ok, err = require_topic(resolved_topic)
        if not ok:
            return {"success": False, "message": err}

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    counter = 1
    while out_path.exists():
        out_path = out_dir / f"{date_str} {stem}_{counter}.md"
        counter += 1

    topic_line = f'topic: "{resolved_topic}"\n' if resolved_topic else ""
    fm = (
        "---\n"
        f"{topic_line}"
        "source: xiaoyi_chat\n"
        f'archived_at: "{datetime.now().isoformat(timespec="seconds")}"\n'
        f'target: "{save_target}"\n'
        "---\n\n"
    )
    body = f"## 问题\n\n{q}\n\n## 回答\n\n{a}\n"
    out_path.write_text(fm + body, encoding="utf-8")
    rel = str(out_path.relative_to(ws))

    append_log(log_action, f"{log_prefix}: {out_path.name}", rel)

    return {"success": True, "path": rel, "message": f"{success_hint}{out_path.name}", "target": save_target}
