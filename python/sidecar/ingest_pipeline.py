"""Unified ingest: convert → classify → index → cascade → wiki sync."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from config import config, is_ignored_dir
from config.settings import NOTES_FOLDER, RAW_FOLDER, WORKSPACE_APP_FOLDER
from modules.file_converter import FileConverterManager
from sidecar.cascade_runner import retry_failed_cascades, run_cascade_for_topics
from sidecar.schema_manager import ensure_schema, needs_schema_setup
from utils.topic_assigner import auto_assign_topic_for_file, sync_wiki_with_files
from utils.topic_file_ops import _check_topic_needs_processing
from utils.wiki_manager import topic_from_notes_path

STAGES = ("schema", "convert", "classify", "index", "cascade", "lint", "sync")

_cancel_event = threading.Event()
_state_lock = threading.Lock()


def _state_path() -> Path | None:
    ws = config.workspace_path
    if not ws:
        return None
    p = Path(ws) / WORKSPACE_APP_FOLDER / "ingest_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_ingest_state() -> dict:
    path = _state_path()
    if not path or not path.exists():
        return {"status": "idle"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "idle"}


def save_ingest_state(state: dict) -> None:
    path = _state_path()
    if not path:
        return
    with _state_lock:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def request_cancel() -> None:
    _cancel_event.set()


def clear_cancel() -> None:
    _cancel_event.clear()


def is_cancelled() -> bool:
    return _cancel_event.is_set()


def _scan_convert_pending(workspace: str) -> list[str]:
    supported = set(FileConverterManager.get_supported_formats())
    ws = Path(workspace)
    pending: list[str] = []
    for f in ws.rglob("*"):
        if not f.is_file() or f.name.startswith("."):
            continue
        rel = f.relative_to(ws)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if RAW_FOLDER in rel.parts:
            continue
        if f.suffix.lower() in supported:
            pending.append(str(f))
    return pending


def _scan_classify_pending(workspace: str) -> list[Path]:
    ws = Path(workspace)
    out: list[Path] = []
    for md in ws.rglob("*.md"):
        if md.name.startswith(".") or "wiki" in md.parts:
            continue
        if any(is_ignored_dir(p) for p in md.parts):
            continue
        if md.name.endswith("_综述.md") or md.name.endswith("综述.md"):
            continue
        try:
            from sidecar.textutils import parse_frontmatter
            text = md.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            if topic_from_notes_path(md):
                continue
            if fm is None or _check_topic_needs_processing(fm):
                out.append(md)
        except OSError:
            continue
    return out


def _index_markdown_files(
    workspace: str,
    files: list[Path],
    progress_cb: Callable[[int, int, str], None] | None,
) -> int:
    from sidecar.rag.chunker import chunk_file
    from sidecar.rag.embedder import encode_documents
    from sidecar.rag.index import add_chunks, delete_by_file
    from sidecar.rag.index_state import file_needs_index, mark_indexed

    indexed = 0
    total = len(files)
    for i, md in enumerate(files):
        if is_cancelled():
            break
        try:
            rel = str(md.relative_to(workspace))
            mtime = md.stat().st_mtime
            if not file_needs_index(rel, mtime, workspace):
                if progress_cb:
                    progress_cb(i + 1, total, f"跳过未改动 ({i + 1}/{total}): {md.name}")
                continue
            if progress_cb:
                progress_cb(i + 1, total, f"索引 ({i + 1}/{total}): {md.name}")
            text = md.read_text(encoding="utf-8")
            chunks = chunk_file(rel, text)
            if not chunks:
                mark_indexed(rel, mtime, workspace)
                continue
            delete_by_file(workspace, rel)
            embeddings = encode_documents([c["content"] for c in chunks])
            add_chunks(workspace, chunks, embeddings)
            mark_indexed(rel, mtime, workspace)
            indexed += 1
        except Exception:
            continue
    return indexed


def run_ingest(
    mode: str = "full",
    file_paths: list[str] | None = None,
    send_progress: Callable[[str, float, str, dict | None], None] | None = None,
    send_event: Callable[[dict], None] | None = None,
) -> dict:
    """
    Run ingest pipeline. *send_progress(stage, progress 0-1, message, extra)*.
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    clear_cancel()
    stats = {
        "converted": 0,
        "classified": 0,
        "pending_topics": 0,
        "indexed_files": 0,
        "cascade_updated": 0,
        "cascade_failed": [],
    }
    state = {
        "status": "running",
        "mode": mode,
        "stage": "schema",
        "started_at": time.time(),
        "stats": stats,
    }
    save_ingest_state(state)

    def prog(stage: str, p: float, msg: str, **extra) -> None:
        state["stage"] = stage
        state["message"] = msg
        save_ingest_state(state)
        if send_progress:
            send_progress(stage, p, msg, extra)

    affected_topics: set[str] = set()

    try:
        ensure_schema(workspace)
        if needs_schema_setup(workspace):
            state["status"] = "needs_schema"
            save_ingest_state(state)
            if send_event:
                send_event({
                    "id": "event",
                    "result": {
                        "type": "ingest_complete",
                        "success": False,
                        "needs_schema": True,
                        "message": "请先完成工作区 Schema 配置",
                    },
                })
            return {"success": False, "needs_schema": True, "message": "请先完成工作区 Schema 配置"}

        prog("schema", 0.02, "schema.md 已就绪…")
        if is_cancelled():
            raise _Cancelled()

        incremental = mode == "incremental"

        # 2. Convert
        if not incremental and not file_paths:
            pending_files = _scan_convert_pending(workspace)
            if pending_files:
                prog("convert", 0.05, f"转换 {len(pending_files)} 个文件…")
                raw_path = str(Path(workspace) / RAW_FOLDER)
                conv = FileConverterManager()
                results = conv.convert_batch(pending_files, workspace, raw_path=raw_path)
                stats["converted"] = sum(1 for r in results if r.get("success"))
            prog("convert", 0.2, f"转换完成: {stats['converted']} 个")
        if is_cancelled():
            raise _Cancelled()

        # 3. Classify
        if incremental and not file_paths:
            to_classify = _scan_classify_pending(workspace)
        elif file_paths:
            to_classify = []
            for raw in file_paths:
                path = Path(raw)
                if not path.is_absolute():
                    path = Path(workspace) / raw
                if path.exists() and path.suffix.lower() == ".md":
                    to_classify.append(path)
        else:
            to_classify = _scan_classify_pending(workspace)
        total_c = max(len(to_classify), 1)
        for i, md in enumerate(to_classify):
            if is_cancelled():
                raise _Cancelled()
            prog("classify", 0.2 + 0.25 * (i + 1) / total_c, f"分类 ({i + 1}/{len(to_classify)}): {md.name}")
            try:
                result = auto_assign_topic_for_file(str(md))
                if result and result.get("status") == "auto_assigned":
                    t = result.get("topic", "")
                    if t:
                        affected_topics.add(t)
                    stats["classified"] += 1
                elif result and result.get("status") == "pending":
                    stats["pending_topics"] += 1
            except Exception:
                continue
        prog("classify", 0.45, f"分类完成: {stats['classified']} 篇，待确认 {stats['pending_topics']}")
        if is_cancelled():
            raise _Cancelled()

        # 4. Index
        ws_path = Path(workspace)
        if incremental and not file_paths:
            index_targets = []
        elif file_paths:
            index_targets = []
            for p in file_paths:
                path = Path(p)
                if not path.is_absolute():
                    path = ws_path / p
                if path.exists() and path.suffix.lower() == ".md" and "wiki" not in path.parts:
                    index_targets.append(path)
        else:
            index_targets = [
                md for md in ws_path.rglob("*.md")
                if not md.name.startswith(".")
                and "wiki" not in md.parts
                and not md.name.endswith("_综述.md")
                and NOTES_FOLDER in md.parts
            ]
        if index_targets:
            prog("index", 0.5, f"检查向量索引 ({len(index_targets)} 篇，仅更新有改动的)…")
            stats["indexed_files"] = _index_markdown_files(
                workspace,
                index_targets,
                lambda cur, tot, msg: prog("index", 0.5 + 0.2 * cur / max(tot, 1), msg),
            )
        prog("index", 0.7, f"索引更新: {stats['indexed_files']} 篇有改动")
        if is_cancelled():
            raise _Cancelled()

        # 5. Cascade — only topics touched this run (+ prior failures via retry)
        cascade_topics = sorted(affected_topics)
        if cascade_topics:
            def cascade_prog(cur: int, tot: int, msg: str) -> None:
                prog("cascade", 0.7 + 0.25 * cur / max(tot, 1), msg)

            cascade_result = run_cascade_for_topics(
                cascade_topics,
                send_response=send_event,
                progress_cb=cascade_prog,
                cancel_check=is_cancelled,
            )
            stats["cascade_updated"] = cascade_result.get("updated", 0)
            stats["cascade_failed"] = cascade_result.get("failed", [])

        # Retry previously failed cascades
        if not is_cancelled():
            retry_result = retry_failed_cascades(send_response=send_event)
            stats["cascade_updated"] += retry_result.get("updated", 0)

        if is_cancelled():
            raise _Cancelled()

        # 6. Lint
        from sidecar.kb_lint import run_kb_lint
        from utils.workspace_log import append_log

        prog("lint", 0.88, "检查断链、孤儿页、过时综述…")
        lint_report = run_kb_lint(workspace)
        stats["lint"] = lint_report.get("summary", {})
        lint_total = stats["lint"].get("total", 0)
        append_log("lint", f"检查完成: {lint_total} 项待关注")
        prog("lint", 0.92, f"Lint 完成: {lint_total} 项")

        if is_cancelled():
            raise _Cancelled()

        # 7. Sync wiki
        prog("sync", 0.95, "同步 WIKI.md…")
        sync_wiki_with_files()

        state["status"] = "complete"
        state["finished_at"] = time.time()
        state["stats"] = stats
        save_ingest_state(state)
        prog("sync", 1.0, "入库流水线完成")

        if send_event:
            send_event({
                "id": "event",
                "result": {
                    "type": "ingest_complete",
                    "success": True,
                    "stats": stats,
                },
            })
        return {"success": True, "stats": stats}

    except _Cancelled:
        state["status"] = "cancelled"
        save_ingest_state(state)
        if send_event:
            send_event({
                "id": "event",
                "result": {"type": "ingest_complete", "success": False, "cancelled": True},
            })
        return {"success": False, "cancelled": True, "stats": stats}

    except Exception as e:
        state["status"] = "failed"
        state["error"] = str(e)
        state["can_retry"] = True
        save_ingest_state(state)
        if send_event:
            send_event({
                "id": "event",
                "result": {"type": "ingest_complete", "success": False, "error": str(e)},
            })
        return {"success": False, "message": str(e), "stats": stats}


class _Cancelled(Exception):
    pass
