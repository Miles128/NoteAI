"""Knowledge base health metrics (PRD success indicators)."""

from __future__ import annotations

from pathlib import Path

from config import config
from config.settings import NOTES_FOLDER
from sidecar.kb_lint import load_lint_report
from utils.link_indexer import load_links
from utils.topic_manager import TopicManager


def _iter_active_topics(tree: list[dict]) -> list[dict]:
    """L1/L2 topics that contain at least one note file."""
    active: list[dict] = []

    def walk(nodes: list[dict]) -> None:
        for node in nodes or []:
            level = int(node.get("level") or 0)
            count = int(node.get("file_count") or 0)
            if level in (1, 2) and count > 0:
                active.append(node)
            walk(node.get("children") or [])

    walk(tree)
    return active


def compute_kb_health(workspace: str | None = None) -> dict:
    ws = workspace or config.workspace_path
    if not ws:
        return {"success": False, "message": "未设置工作区"}

    wp = Path(ws)
    tree = TopicManager.build_tree_from_filesystem(ws)
    active_topics = _iter_active_topics(tree)
    with_survey = sum(1 for t in active_topics if t.get("has_abstract"))
    topic_total = len(active_topics)
    survey_pct = round(100.0 * with_survey / topic_total, 1) if topic_total else 0.0

    note_files: list[str] = []
    notes_root = wp / NOTES_FOLDER
    if notes_root.exists():
        for md in notes_root.rglob("*.md"):
            if md.name.startswith(".") or md.name.endswith("_综述.md"):
                continue
            rel = str(md.relative_to(wp))
            note_files.append(rel)

    outbound: dict[str, int] = {}
    try:
        for link in load_links().get("links", []):
            if link.get("status") != "confirmed":
                continue
            src = link.get("from", "")
            if src.startswith("Notes/"):
                outbound[src] = outbound.get(src, 0) + 1
    except Exception:
        pass

    link_total = sum(outbound.values())
    notes_with_links = len(outbound)
    avg_outbound = round(link_total / len(note_files), 2) if note_files else 0.0

    lint_report = load_lint_report(ws)
    lint_summary = lint_report.get("summary") or {}
    lint_total = int(lint_summary.get("total") or 0)

    pending_count = 0
    try:
        from sidecar.pending_items import collect_pending_items

        pending_count = len(collect_pending_items(ws))
    except Exception:
        pass

    return {
        "success": True,
        "survey_coverage_pct": survey_pct,
        "survey_topics_with": with_survey,
        "survey_topics_total": topic_total,
        "avg_outbound_links": avg_outbound,
        "notes_total": len(note_files),
        "notes_with_outbound": notes_with_links,
        "outbound_links_total": link_total,
        "lint_total": lint_total,
        "lint_summary": lint_summary,
        "pending_total": pending_count,
    }
