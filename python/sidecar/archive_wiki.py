"""Archive RAG chat answers as Notes or wiki markdown."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from config import config
from config.constants import NOTES_FOLDER
from config.settings import ABSTRACT_FOLDER
from sidecar.workspace_rules_validator import check_notes_writable, check_wiki_writable, require_topic
from utils.helpers import sanitize_filename
from utils.wiki_sync import topic_from_notes_path
from utils.workspace_log import append_log

_SAVE_MARKER_RE = re.compile(r"\n?【存档建议】[：:]?\s*(是|否)\s*$", re.MULTILINE)
_SAVE_TARGETS = {"note", "task", "wiki"}


def parse_save_suggestion(text: str) -> tuple[str, bool]:
    """Strip RAG assistant self-assessment marker; return (clean_answer, suggest_save)."""
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


def _markdown_label(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _source_lines(citations: list[dict] | None, *, ws: Path, out_dir: Path) -> list[str]:
    lines = ["## 来源", ""]
    seen: set[tuple[str, str]] = set()
    written = 0
    for position, raw in enumerate(citations or [], start=1):
        if not isinstance(raw, dict):
            continue
        file_path = str(raw.get("file_path") or "").strip()
        url = str(raw.get("url") or "").strip()
        key = (file_path, url)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        index = raw.get("index") or position
        label = _markdown_label(
            raw.get("source_label") or raw.get("file_name") or file_path or url
        )
        section = _markdown_label(raw.get("section_title") or "")
        topic = _markdown_label(raw.get("topic") or "")
        suffix = ""
        if section:
            suffix += f" · {section}"
        if topic:
            suffix += f" · 主题：{topic}"

        link = ""
        if file_path:
            candidate = Path(file_path)
            if not candidate.is_absolute():
                candidate = ws / candidate
            try:
                resolved = candidate.resolve()
                relative_to_workspace = resolved.relative_to(ws.resolve())
            except (OSError, ValueError):
                relative_to_workspace = None
            if relative_to_workspace is not None and resolved.is_file():
                relative_link = os.path.relpath(resolved, out_dir).replace(os.sep, "/")
                link = relative_link
        elif urlparse(url).scheme in {"http", "https"}:
            link = url

        if link:
            lines.append(f"- [{index}] [{label}]({link}){suffix}")
        else:
            missing = _markdown_label(file_path or url)
            lines.append(f"- [{index}] {label}{suffix}（来源当前不可定位：`{missing}`）")
        written += 1
    if not written:
        lines.append("未提供可定位来源。")
    return lines


def archive_chat_answer(
    question: str,
    answer: str,
    topic: str = "",
    title: str = "",
    target: str = "note",
    context_file: str = "",
    citations: list[dict] | None = None,
    preview_only: bool = False,
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
    if save_target not in _SAVE_TARGETS:
        return {"success": False, "message": "不支持的保存目标"}
    if save_target == "wiki":
        ok, err = check_wiki_writable("保存对话到 wiki")
        if not ok:
            return {"success": False, "message": err}
        out_dir = ws / ABSTRACT_FOLDER / "RAG对话"
        log_action = "query_wiki"
        log_prefix = "保存对话到 wiki"
        success_hint = f"已保存到 {ABSTRACT_FOLDER}/RAG对话/"
    else:
        ok, err = check_notes_writable("保存对话笔记")
        if not ok:
            return {"success": False, "message": err}
        out_dir = ws / NOTES_FOLDER / ("待办" if save_target == "task" else "RAG对话")
        log_action = "query"
        log_prefix = "保存对话笔记"
        success_hint = "已保存到 Notes/待办/" if save_target == "task" else "已保存到 Notes/RAG对话/"

    if resolved_topic:
        ok, err = require_topic(resolved_topic)
        if not ok:
            return {"success": False, "message": err}

    out_path = out_dir / filename
    counter = 1
    while out_path.exists():
        out_path = out_dir / f"{date_str} {stem}_{counter}.md"
        counter += 1

    topic_line = f'topic: "{resolved_topic}"\n' if resolved_topic else ""
    fm = (
        "---\n"
        f"{topic_line}"
        "source: rag_chat\n"
        f'archived_at: "{datetime.now().isoformat(timespec="seconds")}"\n'
        f'target: "{save_target}"\n'
        "---\n\n"
    )
    if save_target == "task":
        body = f"# {title or q}\n\n- [ ] {q}\n\n## 参考回答\n\n{a}\n"
    else:
        body = f"## 问题\n\n{q}\n\n## 回答\n\n{a}\n"
    sources = "\n".join(_source_lines(citations, ws=ws, out_dir=out_dir)) + "\n"
    content = fm + body + "\n" + sources
    rel = str(out_path.relative_to(ws))

    if preview_only:
        return {
            "success": True,
            "preview": True,
            "path": rel,
            "content": content,
            "target": save_target,
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    append_log(log_action, f"{log_prefix}: {out_path.name}", rel)

    return {"success": True, "path": rel, "message": f"{success_hint}{out_path.name}", "target": save_target}
