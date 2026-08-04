"""Unified pending inbox: topics, links, lint issues, cascade failures."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from config import config
from sidecar.cascade_runner import load_cascade_failures
from sidecar.kb_lint import auto_fix_broken_links, filter_stale_lint_issues, load_lint_report
from utils.topic_pending import load_pending

_PRIORITY = {
    "ingest": 0,
    "cascade_fail": 1,
    "convert_fail": 1,
    "lint": 2,
    "merge_candidate": 2,
    "topic_merge_candidate": 2,
    "entity_quality": 2,
    "topic": 3,
    "link": 3,
    "link_batch": 3,
}

_MAINTENANCE_LOCK = threading.Lock()
_MAINTENANCE_LAST_RUN: dict[str, float] = {}
_MAINTENANCE_INTERVAL_SECONDS = 30.0


def _lint_action(kind: str) -> str:
    if kind == "stale_survey":
        return "refresh_survey"
    if kind == "orphan_topic":
        return "assign_topic"
    if kind in ("duplicate_content", "near_duplicate"):
        return "review_duplicate"
    if kind == "broken_link":
        return "open_file"
    if kind == "misplaced_note":
        return "assign_topic"
    return "none"


def run_pending_cleanups_if_due(
    workspace: str | None = None,
    *,
    interval_seconds: float = _MAINTENANCE_INTERVAL_SECONDS,
    force: bool = False,
) -> bool:
    """Remove stale rows from topic/link queues before building the inbox."""
    ws = workspace or config.workspace_path
    if not ws:
        return False
    root_key = str(Path(ws).resolve())
    with _MAINTENANCE_LOCK:
        now = time.monotonic()
        elapsed = now - _MAINTENANCE_LAST_RUN.get(root_key, float("-inf"))
        if not force and elapsed < max(0.0, interval_seconds):
            return False
        _MAINTENANCE_LAST_RUN[root_key] = now

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
        try:
            auto_fix_broken_links(ws)
        except Exception:
            pass
    return True


def collect_pending_items(workspace: str | None = None) -> list[dict]:
    ws = workspace or config.workspace_path

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
                "action": "resolve_topic",
            }
        )

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
                "current_topic": issue.get("current_topic", ""),
                "suggested_score": issue.get("suggested_score", 0.0),
                "action": _lint_action(kind),
            }
        )

    if root and root.exists():
        from sidecar.chunk_similarity import load_chunk_similarity_graph
        from sidecar.duplicate_review import is_merge_group_resolved

        similarity_graph = load_chunk_similarity_graph(root)
        chunk_by_id = {chunk.get("id"): chunk for chunk in (similarity_graph.get("chunks") or [])}
        for candidate in similarity_graph.get("candidates") or []:
            files = [str(path) for path in (candidate.get("files") or [])]
            if len(files) < 2 or is_merge_group_resolved(root, files):
                continue
            matches = []
            pair_edges: list[dict] = []
            for row in candidate.get("pairs") or []:
                pair_edges.extend(row.get("matches") or [])
            pair_edges = sorted(pair_edges, key=lambda edge: edge.get("similarity", 0.0), reverse=True)[:5]
            for edge in pair_edges:
                left = chunk_by_id.get(edge.get("source")) or {}
                right = chunk_by_id.get(edge.get("target")) or {}
                matches.append(
                    {
                        "similarity": edge.get("similarity", 0.0),
                        "left": (left.get("content") or "")[:60],
                        "right": (right.get("content") or "")[:60],
                    }
                )
            items.append(
                {
                    "type": "merge_candidate",
                    "files": files,
                    "score": candidate.get("score", 0.0),
                    "content_score": candidate.get("content_score", 0.0),
                    "title_score": candidate.get("title_score", 0.0),
                    "topic_score": candidate.get("topic_score", 0.0),
                    "coverage": candidate.get("coverage", 0.0),
                    "reason": candidate.get("reason", "semantic"),
                    "matches": matches,
                    "action": "review_merge_group",
                }
            )

    if root and root.exists():
        try:
            from sidecar.semantic.store import SemanticStore

            store = SemanticStore(root)
            if store.path.exists():
                with store.connect() as conn:
                    rows = conn.execute(
                        """SELECT id, payload_json, reason FROM review_queue
                           WHERE item_kind = 'entity_quality' AND status = 'pending'
                           ORDER BY created_at DESC"""
                    ).fetchall()
                import json

                for row in rows:
                    payload = json.loads(row["payload_json"] or "{}")
                    items.append(
                        {
                            "type": "entity_quality",
                            "id": row["id"],
                            "message": payload.get("entity_name") or row["reason"],
                            "reason": row["reason"],
                            "rule": payload.get("rule", ""),
                            "entity_id": payload.get("entity_id", ""),
                            "action": "open_entity_quality",
                        }
                    )
        except Exception:
            pass
        for candidate in similarity_graph.get("topic_candidates") or []:
            topics = [str(topic) for topic in (candidate.get("topics") or [])]
            if len(topics) != 2:
                continue
            from config.constants import TOPIC_SEP

            if not all(
                (root / config.NOTES_FOLDER / Path(*[part.strip() for part in topic.split(TOPIC_SEP)])).is_dir()
                for topic in topics
            ):
                continue
            items.append(
                {
                    "type": "topic_merge_candidate",
                    "topics": topics,
                    "score": candidate.get("score", 0.0),
                    "name_score": candidate.get("name_score", 0.0),
                    "content_score": candidate.get("content_score", 0.0),
                    "action": "review_topic_merge",
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
                "action": "retry_cascade",
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
                "action": "retry_convert",
            }
        )

    from sidecar.ingest_pipeline import load_ingest_state

    ingest = load_ingest_state()
    if ingest.get("status") in {"running", "cancelled", "failed", "interrupted"}:
        items.append(
            {
                "type": "ingest",
                "status": ingest.get("status"),
                "stage": ingest.get("stage", ""),
                "message": ingest.get("message", ""),
                "progress": ingest.get("progress"),
                "action": "retry_ingest" if ingest.get("status") != "running" else "none",
                "ts": ingest.get("updated_at", 0),
            }
        )

    for item in items:
        item_type = item.get("type")
        item["priority"] = _PRIORITY.get(item_type, 9) if isinstance(item_type, str) else 9
    return sorted(items, key=lambda item: (item["priority"], -float(item.get("ts") or 0)))
