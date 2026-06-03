"""Unified pending inbox: topics, links, lint issues, cascade failures."""

from __future__ import annotations

from config import config
from sidecar.cascade_runner import load_cascade_failures
from sidecar.kb_lint import load_lint_report
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


def collect_pending_items(workspace: str | None = None) -> list[dict]:
    ws = workspace or config.workspace_path
    items: list[dict] = []

    for p in load_pending():
        items.append({
            "type": "topic",
            "file": p.get("file", ""),
            "title": p.get("title", ""),
            "candidates": p.get("candidates", []),
            "source": p.get("source", ""),
        })

    try:
        for link in load_links().get("links", []):
            if link.get("status") == "pending":
                items.append({
                    "type": "link",
                    "source": link.get("from", ""),
                    "target": link.get("to", ""),
                    "context": link.get("reason", ""),
                })
    except Exception:
        pass

    lint_report = load_lint_report(ws)
    for issue in lint_report.get("issues") or []:
        kind = issue.get("kind") or ""
        if kind == "pending_topics":
            continue
        items.append({
            "type": "lint",
            "lint_kind": kind,
            "severity": issue.get("severity", "info"),
            "message": issue.get("message", ""),
            "file_path": issue.get("file_path", ""),
            "topic": issue.get("topic", ""),
            "action": _lint_action(kind),
        })

    for fail in load_cascade_failures():
        topic = (fail.get("topic") or "").strip()
        if not topic:
            continue
        items.append({
            "type": "cascade_fail",
            "topic": topic,
            "error": fail.get("error", ""),
            "ts": fail.get("ts", 0),
        })

    from sidecar.convert_failures import load_convert_failures

    for fail in load_convert_failures():
        path = (fail.get("file") or "").strip()
        if not path:
            continue
        items.append({
            "type": "convert_fail",
            "file": path,
            "error": fail.get("error", ""),
            "ts": fail.get("ts", 0),
        })

    return items
