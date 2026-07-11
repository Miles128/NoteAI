"""Home dashboard status aggregation."""

from __future__ import annotations

from pathlib import Path

from config import config
from config.constants import NOTES_FOLDER
from sidecar import job_status
from sidecar.cascade_runner import load_cascade_failures
from sidecar.ingest_pipeline import normalize_ingest_state, prepare_auto_ingest
from sidecar.kb_lint import load_lint_report
from sidecar.pending_items import collect_pending_items


def _is_readme_note(path: Path) -> bool:
    return path.suffix.lower() == ".md" and path.stem.casefold() == "readme"


def workspace_stats(workspace: str) -> dict:
    notes_root = Path(workspace) / NOTES_FOLDER
    notes = 0
    topics: set[str] = set()
    if notes_root.exists():
        for path in notes_root.rglob("*.md"):
            if path.name.startswith(".") or _is_readme_note(path):
                continue
            notes += 1
            try:
                rel = path.parent.relative_to(notes_root)
            except ValueError:
                continue
            if str(rel) != ".":
                topics.update(str(rel).split("/"))
    return {"notes": notes, "topics": len({t for t in topics if t})}


def pending_summary(pending: dict, lint_report: dict) -> dict:
    items = pending.get("items") if isinstance(pending.get("items"), list) else []
    cascade = load_cascade_failures()
    try:
        from sidecar.convert_failures import load_convert_failures

        convert = load_convert_failures()
    except Exception:
        convert = []
    lint_summary = lint_report.get("summary") if isinstance(lint_report, dict) else {}
    lint_total = int(lint_summary.get("total") or 0) if isinstance(lint_summary, dict) else 0
    return {
        "count": len(items) + len(cascade) + len(convert) + lint_total,
        "topics": len([x for x in items if x.get("kind") == "topic" or x.get("type") == "topic"]),
        "links": len([x for x in items if x.get("kind") == "link" or x.get("type") == "link"]),
        "cascade": len(cascade),
        "convert": len(convert),
        "lint": lint_total,
    }


def rag_index_status(workspace: str) -> dict:
    if not config.rag_enabled:
        return {"success": True, "enabled": False, "built": False}
    try:
        from sidecar.rag.index import count_indexed_chunks, index_exists, load_manifest

        chunk_count = count_indexed_chunks(workspace)
        manifest = load_manifest(workspace)
        expected_chunks = sum(len(entry.get("chunks") or []) for entry in manifest.get("files", {}).values())
        built = index_exists(workspace) and chunk_count > 0 and chunk_count == expected_chunks
        return {
            "success": True,
            "enabled": True,
            "built": built,
            "needs_rebuild": not built,
            "repair_required": expected_chunks > 0 and chunk_count != expected_chunks,
            "chunk_count": chunk_count,
            "expected_chunks": expected_chunks,
            "file_count": len(manifest.get("files", {})),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def ingest_status() -> dict:
    state = normalize_ingest_state()
    status = state.get("status", "idle")
    return {
        "status": status,
        "stage": state.get("stage", ""),
        "progress": state.get("progress", 0),
        "message": state.get("message", ""),
        "stats": state.get("stats", {}),
        "running": status == "running",
        "needs_resume": status in ("interrupted", "failed"),
        "can_retry": status in ("failed", "cancelled", "interrupted", "complete"),
    }


def get_dashboard_status(workspace: str) -> dict:
    pending = {"items": collect_pending_items(workspace)}
    return {
        "success": True,
        "stats": workspace_stats(workspace),
        "pending": pending,
        "pending_summary": pending_summary(pending, load_lint_report()),
        "ingest": ingest_status(),
        "jobs": job_status.list_jobs(include_finished=True, limit=50),
        "update_plan": prepare_auto_ingest(workspace),
        "index": rag_index_status(workspace),
    }
