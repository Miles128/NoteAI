"""Unified pending inbox: topics, links, lint issues, cascade failures."""

from __future__ import annotations

from pathlib import Path

from config import config
from sidecar.cascade_runner import load_cascade_failures
from sidecar.kb_lint import auto_fix_broken_links, filter_stale_lint_issues, load_lint_report
from utils.link_indexer import load_links
from utils.topic_assigner import load_pending


def _lint_action(kind: str) -> str:
    if kind == "stale_survey":
        return "refresh_survey"
    if kind == "orphan_topic":
        return "assign_topic"
    if kind == "broken_link":
        return "open_file"
    return "none"


def _run_pending_cleanups() -> None:
    """Remove stale rows from topic/link queues before building the inbox."""
    ws = config.workspace_path
    try:
        from utils.topic_assigner import sync_all_folder_topics

        sync_all_folder_topics(ws)
    except Exception:
        pass
    try:
        from utils.topic_pending import cleanup_stale_pending

        cleanup_stale_pending()
    except Exception:
        pass
    try:
        from utils.link_indexer import cleanup_stale_links

        cleanup_stale_links()
    except Exception:
        pass
    try:
        from sidecar.convert_failures import cleanup_stale_convert_failures

        cleanup_stale_convert_failures()
    except Exception:
        pass
    if ws:
        try:
            auto_fix_broken_links(ws)
        except Exception:
            pass


def collect_pending_items(workspace: str | None = None) -> list[dict]:
    ws = workspace or config.workspace_path
    _run_pending_cleanups()

    items: list[dict] = []
    topic_files: set[str] = set()

    for p in load_pending():
        rel = p.get("file", "")
        if rel:
            topic_files.add(rel)
        items.append(
            {
                "type": "topic",
                "file": rel,
                "title": p.get("title", ""),
                "candidates": p.get("candidates", []),
                "source": p.get("source", ""),
            }
        )

    try:
        pending_links = [link for link in load_links().get("links", []) if link.get("status") == "pending"]
        if pending_links:
            items.append(
                {
                    "type": "link_batch",
                    "count": len(pending_links),
                    "message": f"{len(pending_links)} 条待确认链接",
                }
            )
    except Exception:
        pass

    root = Path(ws) if ws else None
    lint_report = load_lint_report(ws)
    issues = lint_report.get("issues") or []
    if root and root.exists():
        issues = filter_stale_lint_issues(issues, root)

    for issue in issues:
        kind = issue.get("kind") or ""
        if kind == "pending_topics":
            continue
        rel = (issue.get("file_path") or "").strip()
        if kind == "orphan_topic" and rel in topic_files:
            continue
        items.append(
            {
                "type": "lint",
                "lint_kind": kind,
                "severity": issue.get("severity", "info"),
                "message": issue.get("message", ""),
                "file_path": rel,
                "topic": issue.get("topic", ""),
                "action": _lint_action(kind),
            }
        )

    for fail in load_cascade_failures():
        topic = (fail.get("topic") or "").strip()
        if not topic:
            continue
        items.append(
            {
                "type": "cascade_fail",
                "topic": topic,
                "error": fail.get("error", ""),
                "ts": fail.get("ts", 0),
            }
        )

    from sidecar.convert_failures import load_convert_failures

    for fail in load_convert_failures():
        path = (fail.get("file") or "").strip()
        if not path:
            continue
        if root and root.exists():
            full = root / path if not Path(path).is_absolute() else Path(path)
            if not full.exists():
                continue
        items.append(
            {
                "type": "convert_fail",
                "file": path,
                "error": fail.get("error", ""),
                "ts": fail.get("ts", 0),
            }
        )

    return items
