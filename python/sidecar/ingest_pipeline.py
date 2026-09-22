"""Unified ingest: convert → classify → index → cascade → wiki sync."""

from __future__ import annotations

import time
from collections.abc import Callable
from time import monotonic
from typing import Any

from config import config
from modules.file_converter import FileConverterManager
from sidecar.ingest_index import (
    _index_markdown_files,
    _purge_deleted_index_files,
)
from sidecar.ingest_scan import (
    _scan_classify_pending,
    _scan_index_pending,
    scan_convert_pending,
)
from sidecar.ingest_stages import (
    Cancelled,
    IngestCtx,
    raise_if_cancelled,
    run_cascade_stage,
    run_classify_stage,
    run_compile_stage,
    run_convert_stage,
    run_crossref_stage,
    run_index_stage,
    run_lint_stage,
    run_placement,
    run_semantic_stage,
    run_sync_stage,
)
from sidecar.ingest_state import (
    _save_fingerprint,
    _workspace_files_changed,
    cancel_generation,
    clear_cancel,
    is_cancelled,
    load_ingest_state,
    normalize_ingest_state,
    request_cancel,
    save_ingest_state,
)
from sidecar.workspace_rules import needs_workspace_rules_setup
from utils.topic.assigner import auto_assign_topic_for_file, sync_wiki_with_files

STAGES = (
    "rules",
    "convert",
    "compile",
    "classify",
    "semantic",
    "index",
    "crossref",
    "cascade",
    "lint",
    "sync",
)


# ingest 进度写盘节流间隔（秒）：避免千级文件全量导入时每次 mkstemp+fsync
_PROG_SAVE_INTERVAL_SECS = 0.5

__all__ = [
    "STAGES",
    "FileConverterManager",
    "auto_assign_topic_for_file",
    "cancel_generation",
    "clear_cancel",
    "is_cancelled",
    "load_ingest_state",
    "normalize_ingest_state",
    "prepare_auto_ingest",
    "request_cancel",
    "request_full_ingest",
    "run_ingest",
    "save_ingest_state",
    "sync_wiki_with_files",
    "_index_markdown_files",
    "_purge_deleted_index_files",
    "_scan_classify_pending",
    "scan_convert_pending",
    "_scan_index_pending",
]


def _workspace_has_pending_ingest(workspace: str) -> bool:
    # Fast path: if no tracked files have changed since last scan, skip heavy checks.
    changed, _ = _workspace_files_changed(workspace)
    if not changed:
        return False

    if scan_convert_pending(workspace):
        return True
    if _scan_classify_pending(workspace):
        return True
    if _scan_index_pending(workspace):
        return True
    try:
        from utils.note_compiler import scan_compile_pending

        if scan_compile_pending(workspace):
            return True
    except Exception:
        pass
    return False


def prepare_auto_ingest(
    workspace: str | None = None,
    file_paths: list[str] | None = None,
) -> dict:
    """
    Decide whether ingest should start automatically.
    Returns dict with ``action`` in (``start``, ``none``).
    """
    ws = workspace or config.workspace_path
    if not ws:
        return {"action": "none", "message": "未设置工作区"}

    if not config.ingest_auto_enabled:
        return {"action": "none", "reason": "auto_disabled"}

    state = load_ingest_state()
    status = state.get("status", "idle")

    if needs_workspace_rules_setup(ws):
        return {"action": "none", "needs_workspace_rules": True}

    if file_paths:
        return {
            "action": "start",
            "mode": "incremental",
            "file_paths": list(file_paths),
            "resume": False,
        }

    if state.get("force_full_next"):
        return {
            "action": "start",
            "mode": "full",
            "file_paths": [],
            "resume": False,
            "force_full": True,
        }

    if status in ("interrupted", "failed"):
        return {
            "action": "start",
            "mode": state.get("mode", "full"),
            "file_paths": state.get("file_paths") or [],
            "resume": True,
        }

    has_work = _workspace_has_pending_ingest(ws)
    never_completed = not state.get("last_complete_at") and status != "complete"

    if status == "complete" and not has_work:
        return {"action": "none", "reason": "up_to_date"}

    if never_completed or scan_convert_pending(ws):
        mode = "full"
    else:
        mode = "incremental"

    if not has_work and status == "complete":
        return {"action": "none", "reason": "up_to_date"}

    return {
        "action": "start",
        "mode": mode,
        "file_paths": [],
        "resume": status in ("interrupted", "failed"),
    }


def request_full_ingest() -> None:
    """Mark next auto-ingest as full pipeline (e.g. after Schema wizard)."""
    state = load_ingest_state()
    state["force_full_next"] = True
    save_ingest_state(state)


def run_ingest(
    mode: str = "full",
    file_paths: list[str] | None = None,
    send_progress: Callable[[str, float, str, dict | None], None] | None = None,
    send_event: Callable[[dict], None] | None = None,
    *,
    resume: bool = False,
    cancel_after_generation: int | None = None,
) -> dict:
    """
    Run ingest pipeline. *send_progress(stage, progress 0-1, message, extra)*.
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    # A scheduled worker receives the generation captured before it was
    # enqueued. Any later request_cancel() is therefore observed even if it
    # arrives before this function starts running.
    if cancel_after_generation is None:
        current_generation = cancel_generation()
        cancel_after_generation = current_generation - 1 if is_cancelled() else current_generation

    def cancelled() -> bool:
        return cancel_generation() > cancel_after_generation

    # 进度写盘节流状态（见 prog()）
    _last_prog_save: float = 0.0

    # Previous completion metadata is also required by the non-resume
    # incremental fast path. Resume only controls whether partial stage state
    # and statistics are restored below.
    prev = load_ingest_state()
    stats: dict[str, Any] = {
        "converted": 0,
        "compiled": 0,
        "classified": 0,
        "pending_topics": 0,
        "indexed_files": 0,
        "semantic_documents": 0,
        "semantic_blocks": 0,
        "semantic_extracted_blocks": 0,
        "semantic_failed_blocks": 0,
        "semantic_pending_documents": 0,
        "semantic_failures": [],
        "cascade_updated": 0,
        "cascade_failed": [],
        "cascade_topics": [],
    }
    if resume and isinstance(prev.get("stats"), dict):
        stats.update({k: prev["stats"].get(k, v) for k, v in stats.items() if k in prev["stats"]})

    if prev.get("force_full_next"):
        mode = "full"
        resume = False

    # Skip startup-style incremental checks when the workspace is already up to date.
    if (
        mode == "incremental"
        and not file_paths
        and not resume
        and prev.get("status") == "complete"
        and prev.get("last_complete_at")
        and not _workspace_has_pending_ingest(workspace)
    ):
        msg = "工作区已是最新，跳过自检"
        if send_progress:
            send_progress("sync", 1.0, msg, None)
        if send_event:
            send_event(
                {
                    "id": "event",
                    "result": {"type": "ingest_complete", "success": True, "up_to_date": True, "message": msg},
                }
            )
        # Save current fingerprint even when skipped, so restarts stay fast.
        _, fingerprint = _workspace_files_changed(workspace)
        _save_fingerprint(workspace, fingerprint)
        return {"success": True, "up_to_date": True, "message": msg}

    state: dict[str, Any] = {
        "status": "running",
        "mode": mode,
        "stage": "rules",
        "started_at": time.time(),
        "stats": stats,
        "file_paths": list(file_paths or []),
        "resume": resume,
    }
    state.pop("force_full_next", None)
    if resume and prev.get("completed_stages"):
        state["completed_stages"] = list(prev["completed_stages"])
        if "index" in state["completed_stages"] and isinstance(prev.get("pending_crossref_paths"), list):
            state["pending_crossref_paths"] = list(prev["pending_crossref_paths"])
        if "classify" in state["completed_stages"] and isinstance(prev.get("affected_topics"), list):
            state["affected_topics"] = list(prev["affected_topics"])
    save_ingest_state(state)

    raw_completed_stages = state.get("completed_stages")
    completed_stages = (
        {str(stage) for stage in raw_completed_stages} if isinstance(raw_completed_stages, list) else set()
    )

    def stage_done(name: str) -> bool:
        return resume and name in completed_stages

    def mark_stage_done(name: str) -> None:
        completed_stages.add(name)
        state["completed_stages"] = [s for s in STAGES if s in completed_stages]
        state["stats"] = stats
        save_ingest_state(state)

    def prog(stage: str, p: float, msg: str, **extra) -> None:
        nonlocal _last_prog_save
        state["stage"] = stage
        state["progress"] = p
        state["message"] = msg
        # 进度写盘节流：全量导入千级文件时避免每次 mkstemp+fsync
        # （结束帧 p>=1.0 强制落盘，保证最终状态可恢复）
        now = monotonic()
        if p >= 1.0 or now - _last_prog_save >= _PROG_SAVE_INTERVAL_SECS:
            _last_prog_save = now
            save_ingest_state(state)
        if send_progress:
            send_progress(stage, p, msg, extra)

    raw_affected_topics = state.get("affected_topics")
    affected_topics: set[str] = (
        {str(topic) for topic in raw_affected_topics} if isinstance(raw_affected_topics, list) else set()
    )

    try:
        if needs_workspace_rules_setup(workspace):
            state["status"] = "needs_workspace_rules"
            save_ingest_state(state)
            if send_event:
                send_event(
                    {
                        "id": "event",
                        "result": {
                            "type": "ingest_complete",
                            "success": False,
                            "needs_workspace_rules": True,
                            "message": "请先在设置 → 整理规则中完成工作区配置",
                        },
                    }
                )
            return {
                "success": False,
                "needs_workspace_rules": True,
                "message": "请先在设置 → 整理规则中完成工作区配置",
            }

        prog("rules", 0.02, "整理规则已就绪…")
        mark_stage_done("rules")
        if cancelled():
            raise Cancelled()

        ctx = IngestCtx(
            workspace=workspace,
            mode=mode,
            file_paths=file_paths,
            incremental=mode == "incremental",
            state=state,
            stats=stats,
            affected_topics=affected_topics,
            cancelled=cancelled,
            prog=prog,
            stage_done=stage_done,
            mark_stage_done=mark_stage_done,
        )
        run_convert_stage(ctx)
        raise_if_cancelled(ctx)
        run_compile_stage(ctx)
        raise_if_cancelled(ctx)
        run_classify_stage(ctx)
        raise_if_cancelled(ctx)
        run_placement(ctx)
        run_semantic_stage(ctx)
        raise_if_cancelled(ctx)
        run_index_stage(ctx)
        raise_if_cancelled(ctx)
        run_crossref_stage(ctx)
        raise_if_cancelled(ctx)
        run_cascade_stage(ctx)
        raise_if_cancelled(ctx)
        run_lint_stage(ctx)
        raise_if_cancelled(ctx)
        run_sync_stage(ctx)

        state["status"] = "complete"
        state["finished_at"] = time.time()
        state["last_complete_at"] = time.time()
        state["stats"] = stats
        state["completed_stages"] = []
        state.pop("pending_crossref_paths", None)
        state.pop("affected_topics", None)
        state.pop("error", None)
        save_ingest_state(state)
        # Save fingerprint so next startup can skip heavy scans when nothing changed.
        _, fingerprint = _workspace_files_changed(workspace)
        _save_fingerprint(workspace, fingerprint)
        prog("sync", 1.0, "入库流水线完成")

        if send_event:
            send_event(
                {
                    "id": "event",
                    "result": {
                        "type": "ingest_complete",
                        "success": True,
                        "stats": stats,
                        "cascade_topics": stats.get("cascade_topics", []),
                    },
                }
            )
        return {"success": True, "stats": stats}

    except Cancelled:
        state["status"] = "cancelled"
        state["cancelled_at"] = time.time()
        save_ingest_state(state)
        clear_cancel()
        if send_event:
            send_event(
                {
                    "id": "event",
                    "result": {"type": "ingest_complete", "success": False, "cancelled": True},
                }
            )
        return {"success": False, "cancelled": True, "stats": stats}

    except Exception as e:
        state["status"] = "failed"
        state["error"] = str(e)
        state["can_retry"] = True
        state["stats"] = stats
        save_ingest_state(state)
        if send_event:
            send_event(
                {
                    "id": "event",
                    "result": {"type": "ingest_complete", "success": False, "error": str(e)},
                }
            )
        return {"success": False, "message": str(e), "stats": stats}
