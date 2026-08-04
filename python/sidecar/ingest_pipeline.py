"""Unified ingest: convert → classify → index → cascade → wiki sync."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from config import config, is_ignored_dir
from config.settings import NOTES_FOLDER, RAW_FOLDER, WORKSPACE_APP_FOLDER
from modules.file_converter import FileConverterManager
from sidecar.workspace_rules import needs_workspace_rules_setup
from utils.logger import logger
from utils.topic_assigner import auto_assign_topic_for_file, sync_wiki_with_files
from utils.topic_file_ops import _check_topic_needs_processing
from utils.wiki_sync import topic_from_notes_path

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

_cancel_event = threading.Event()
_cancel_lock = threading.Lock()
_cancel_generation = 0
_state_lock = threading.Lock()


def _state_path() -> Path | None:
    ws = config.workspace_path
    if not ws:
        return None
    p = Path(ws) / WORKSPACE_APP_FOLDER / "ingest_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _fingerprint_path(workspace: str) -> Path:
    p = Path(workspace) / WORKSPACE_APP_FOLDER / "ingest_fingerprint.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_fingerprint(workspace: str) -> dict:
    path = _fingerprint_path(workspace)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_fingerprint(workspace: str, fingerprint: dict) -> None:
    path = _fingerprint_path(workspace)
    try:
        _write_json_atomic(path, fingerprint)
    except OSError as e:
        logger.warning("[ingest] failed to save fingerprint: %s", e)


def _workspace_file_fingerprint(workspace: str) -> dict:
    """Fast fingerprint of tracked files: path -> [mtime, size]."""
    ws = Path(workspace)
    supported = set(FileConverterManager.get_supported_formats())
    fingerprint: dict = {}
    for f in ws.rglob("*"):
        if not f.is_file() or f.name.startswith("."):
            continue
        rel = f.relative_to(ws)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if any(is_ignored_dir(p) for p in rel.parts):
            continue
        if WORKSPACE_APP_FOLDER in rel.parts or "wiki" in rel.parts or RAW_FOLDER in rel.parts:
            continue
        suffix = f.suffix.lower()
        is_md = suffix == ".md"
        is_convertible = suffix in supported
        if not is_md and not is_convertible:
            continue
        try:
            stat = f.stat()
            fingerprint[str(rel).replace("\\", "/")] = [stat.st_mtime, stat.st_size]
        except OSError:
            continue
    return fingerprint


def _workspace_files_changed(workspace: str) -> tuple[bool, dict]:
    """Return (changed, current_fingerprint).

    Uses mtime + size as the change signal. A full hash is computed only when
    mtime/size match but we still want to be safe, which is skipped here for
    speed; callers fall back to content checks when needed.
    """
    current = _workspace_file_fingerprint(workspace)
    previous = _load_fingerprint(workspace)
    if previous == current:
        return False, current
    return True, current


def load_ingest_state() -> dict:
    path = _state_path()
    if not path or not path.exists():
        return {"status": "idle"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"status": "idle"}
    except (OSError, json.JSONDecodeError):
        return {"status": "idle"}


def save_ingest_state(state: dict) -> None:
    path = _state_path()
    if not path:
        return
    with _state_lock:
        _write_json_atomic(path, state)


def _write_json_atomic(path: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def request_cancel() -> None:
    global _cancel_generation
    with _cancel_lock:
        _cancel_generation += 1
        _cancel_event.set()


def clear_cancel() -> None:
    _cancel_event.clear()


def is_cancelled() -> bool:
    return _cancel_event.is_set()


def cancel_generation() -> int:
    with _cancel_lock:
        return _cancel_generation


def normalize_ingest_state() -> dict:
    """Mark orphaned ``running`` state (process killed mid-pipeline) as interrupted."""
    state = load_ingest_state()
    if state.get("status") == "running":
        state["status"] = "interrupted"
        state["interrupted_at"] = time.time()
        msg = (state.get("message") or "").strip()
        if "续跑" not in msg:
            state["message"] = (msg + " — 上次未跑完，将自动续跑").strip(" —")
        save_ingest_state(state)
    return state


def _workspace_has_pending_ingest(workspace: str) -> bool:
    # Fast path: if no tracked files have changed since last scan, skip heavy checks.
    changed, _ = _workspace_files_changed(workspace)
    if not changed:
        return False

    if _scan_convert_pending(workspace):
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

    if never_completed or _scan_convert_pending(ws):
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


def _scan_index_pending(workspace: str) -> list[Path]:
    """Markdown under Notes/ whose mtime differs from last indexed state."""
    from sidecar.rag.index_state import file_needs_index

    ws = Path(workspace)
    out: list[Path] = []
    for md in ws.rglob("*.md"):
        if (
            md.name.startswith(".")
            or any(part.startswith(".") for part in md.relative_to(ws).parts[:-1])
            or "wiki" in md.parts
        ):
            continue
        if md.name.endswith("_综述.md"):
            continue
        if NOTES_FOLDER not in md.parts:
            continue
        try:
            rel = str(md.relative_to(ws))
            if file_needs_index(rel, md.stat().st_mtime, workspace):
                out.append(md)
        except OSError:
            continue
    return out


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
        if md.name == "schema.md" or NOTES_FOLDER not in md.parts:
            continue
        from sidecar.workspace_meta import is_inbox_orphan_path, is_workspace_meta_path

        if is_workspace_meta_path(md):
            continue
        if not is_inbox_orphan_path(md, workspace):
            continue
        try:
            from utils.text_utils import parse_frontmatter

            text = md.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            if topic_from_notes_path(md):
                continue
            if not is_inbox_orphan_path(md, workspace):
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
    cancelled: Callable[[], bool] = is_cancelled,
) -> tuple[int, list[str]]:
    from sidecar.rag.index import index_operation

    with index_operation(workspace, blocking=False) as acquired:
        if not acquired:
            raise RuntimeError("RAG 索引正在由另一个任务更新，请稍后重试")
        return _index_markdown_files_locked(workspace, files, progress_cb, cancelled)


def _index_markdown_files_locked(
    workspace: str,
    files: list[Path],
    progress_cb: Callable[[int, int, str], None] | None,
    cancelled: Callable[[], bool],
) -> tuple[int, list[str]]:
    if not config.rag_enabled:
        return 0, []

    from sidecar.rag.chunker import chunk_file
    from sidecar.rag.embedder import encode_documents
    from sidecar.rag.index import count_indexed_chunks, load_manifest, replace_file_chunks
    from sidecar.rag.index_state import file_needs_index, mark_many_indexed

    manifest = load_manifest(workspace)
    expected_chunks = sum(len(entry.get("chunks") or []) for entry in manifest.get("files", {}).values())
    actual_chunks = count_indexed_chunks(workspace, allow_metadata_fallback=False)
    if actual_chunks < 0:
        raise RuntimeError("RAG 索引当前不可访问，请关闭其他 NoteAI 实例后重试")
    repair_all = expected_chunks > 0 and actual_chunks != expected_chunks
    if repair_all:
        logger.warning(
            "[ingest/index] integrity mismatch actual=%s expected=%s; repairing all notes",
            actual_chunks,
            expected_chunks,
        )
        ws_path = Path(workspace)
        files = [
            md
            for md in ws_path.rglob("*.md")
            if not md.name.startswith(".")
            and not any(part.startswith(".") for part in md.relative_to(ws_path).parts[:-1])
            and "wiki" not in md.parts
            and NOTES_FOLDER in md.parts
            and not md.name.endswith("_综述.md")
        ]

    indexed = 0
    indexed_paths: list[str] = []
    total = len(files)
    replacements: dict[str, dict] = {}
    pending_updates: dict[str, float] = {}
    preparation_errors: list[str] = []

    for i, md in enumerate(files):
        if cancelled():
            break
        try:
            rel = str(md.relative_to(workspace))
            mtime = md.stat().st_mtime
            if not repair_all and not file_needs_index(rel, mtime, workspace):
                if progress_cb:
                    progress_cb(i + 1, total, f"跳过未改动 ({i + 1}/{total}): {md.name}")
                continue
            if progress_cb:
                progress_cb(i + 1, total, f"索引 ({i + 1}/{total}): {md.name}")
            text = md.read_text(encoding="utf-8")
            chunks = chunk_file(rel, text)
            if not chunks:
                replacements[rel] = {
                    "chunks": [],
                    "embeddings": [],
                    "mtime": mtime,
                    "size": md.stat().st_size,
                }
                pending_updates[rel] = mtime
                continue
            embeddings = encode_documents([c["content"] for c in chunks])
            replacements[rel] = {
                "chunks": chunks,
                "embeddings": embeddings,
                "mtime": mtime,
                "size": md.stat().st_size,
            }
            pending_updates[rel] = mtime
        except Exception as e:
            logger.warning("[ingest/index] failed to prepare %s: %s", md, e)
            preparation_errors.append(f"{md.name}: {e}")
            continue

    if preparation_errors:
        raise RuntimeError(f"索引准备失败 {len(preparation_errors)} 篇: {'; '.join(preparation_errors[:3])}")

    # Do not mutate the index after cancellation. Prepared embeddings can be
    # safely discarded and the unchanged state will cause a retry next run.
    if cancelled():
        return 0, []

    if pending_updates:
        replace_file_chunks(workspace, replacements)
        mark_many_indexed(pending_updates, workspace)
        indexed = len(pending_updates)
        indexed_paths = list(pending_updates)

    return indexed, indexed_paths


def _purge_deleted_index_files(workspace: str) -> list[str]:
    """Remove chunks and state entries for Notes files deleted from disk."""
    if not config.rag_enabled:
        return []

    from sidecar.rag.index import delete_by_file
    from sidecar.rag.index_state import load_state, remove_indexed

    ws = Path(workspace)
    stale_paths = [rel for rel in load_state(workspace) if not (ws / rel).is_file()]
    for rel in stale_paths:
        delete_by_file(workspace, rel)
    remove_indexed(stale_paths, workspace)
    return stale_paths


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
        "semantic_claims": 0,
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
        state["stage"] = stage
        state["progress"] = p
        state["message"] = msg
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
            raise _Cancelled()

        incremental = mode == "incremental"
        converted_note_paths: list[str] = []

        # 2. Convert
        if stage_done("convert"):
            prog("convert", 0.16, "跳过转换（已完成）")
        elif not incremental and not file_paths:
            pending_files = _scan_convert_pending(workspace)
            if pending_files:
                prog("convert", 0.05, f"转换 {len(pending_files)} 个文件…")
                raw_path = str(Path(workspace) / RAW_FOLDER)
                conv = FileConverterManager()
                output_path = str(Path(workspace) / NOTES_FOLDER)
                results = conv.convert_batch(pending_files, output_path, raw_path=raw_path, assign_topic=False)
                stats["converted"] = sum(1 for r in results if r.get("success"))
                failed_conversions = [r for r in results if not r.get("success")]
                for r in results:
                    if r.get("success") and r.get("output_path"):
                        out = Path(r["output_path"])
                        try:
                            converted_note_paths.append(str(out.relative_to(workspace)))
                        except ValueError:
                            converted_note_paths.append(r["output_path"])
                if failed_conversions:
                    first_error = failed_conversions[0].get("error") or "未知错误"
                    raise RuntimeError(f"文件转换失败 {len(failed_conversions)} 个: {first_error}")
            prog("convert", 0.16, f"转换完成: {stats['converted']} 个")
            mark_stage_done("convert")
        else:
            prog("convert", 0.16, "无需转换")
            mark_stage_done("convert")
        if cancelled():
            raise _Cancelled()

        # 2b. Compile — rule + LLM rewrite for converted/imported notes
        if stage_done("compile"):
            prog("compile", 0.28, "跳过笔记编译（已完成）")
        else:
            from utils.note_compiler import compile_notes_batch, scan_compile_pending

            compile_targets: list[str] = list(converted_note_paths)
            if file_paths:
                ws_path = Path(workspace)
                for raw in file_paths:
                    path = Path(raw)
                    if not path.is_absolute():
                        path = ws_path / raw
                    if path.exists() and path.suffix.lower() == ".md":
                        rel = str(path.relative_to(ws_path))
                        if rel not in compile_targets:
                            compile_targets.append(rel)
            for rel in scan_compile_pending(workspace):
                if rel not in compile_targets:
                    compile_targets.append(rel)

            if compile_targets:
                prog("compile", 0.17, f"笔记编译 ({len(compile_targets)} 篇)…")
                stats["compiled"], _ = compile_notes_batch(
                    compile_targets,
                    progress_cb=lambda cur, tot, msg: prog("compile", 0.17 + 0.11 * cur / max(tot, 1), msg),
                )
            prog("compile", 0.28, f"笔记编译完成: {stats['compiled']} 篇")
            mark_stage_done("compile")
        if cancelled():
            raise _Cancelled()

        # 3. Classify
        if stage_done("classify"):
            prog("classify", 0.45, "跳过分类（已完成）")
        else:
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
            classify_errors: list[str] = []
            for i, md in enumerate(to_classify):
                if cancelled():
                    raise _Cancelled()
                prog("classify", 0.28 + 0.17 * (i + 1) / total_c, f"分类 ({i + 1}/{len(to_classify)}): {md.name}")
                try:
                    result = auto_assign_topic_for_file(str(md))
                    if result and result.get("status") == "auto_assigned":
                        t = result.get("topic", "")
                        if t:
                            affected_topics.add(t)
                        stats["classified"] += 1
                    elif result and result.get("status") == "pending":
                        stats["pending_topics"] += 1
                    elif result and result.get("status") == "error":
                        classify_errors.append(f"{md.name}: {result.get('message', '未知错误')}")
                except Exception as e:
                    classify_errors.append(f"{md.name}: {e}")
            state["affected_topics"] = sorted(affected_topics)
            state["stats"] = stats
            save_ingest_state(state)
            if classify_errors:
                raise RuntimeError(f"分类失败 {len(classify_errors)} 篇: {'; '.join(classify_errors[:3])}")
            prog("classify", 0.45, f"分类完成: {stats['classified']} 篇，待确认 {stats['pending_topics']}")
            mark_stage_done("classify")
        if cancelled():
            raise _Cancelled()

        # Re-evaluate already-filed notes before indexing so automatic moves do
        # not leave the vector manifest pointing at their former paths.
        from sidecar.topic_placement import auto_move_misplaced_notes

        placement_result = auto_move_misplaced_notes(workspace)
        placement_moves = placement_result.get("moved") or []
        stats["auto_topic_moves"] = len(placement_moves)
        for move in placement_moves:
            for topic in (move.get("current_topic"), move.get("suggested_topic")):
                if topic:
                    affected_topics.add(str(topic))

        # 3b. Semantic compile — evidence-first IR. Failures are recorded but
        # do not block the established classify/index/wiki pipeline.
        if stage_done("semantic"):
            prog("semantic", 0.52, "跳过语义编译（已完成）")
        elif not config.semantic_compile_enabled:
            prog("semantic", 0.52, "语义编译已关闭")
            mark_stage_done("semantic")
        else:
            from sidecar.semantic.compiler import compile_semantic_batch
            from sidecar.semantic.object_wiki import materialize_object_collection
            from sidecar.semantic.store import SemanticStore
            from sidecar.semantic.topic_state import materialize_topic_state
            from sidecar.semantic.wiki import materialize_topic_wiki_page

            ws_path = Path(workspace)
            store = SemanticStore(workspace)
            removed_topics = set(store.purge_missing_documents())
            if incremental:
                semantic_targets = _scan_index_pending(workspace)
            else:
                semantic_targets = [
                    md
                    for md in ws_path.rglob("*.md")
                    if not md.name.startswith(".")
                    and "wiki" not in md.parts
                    and NOTES_FOLDER in md.parts
                    and not md.name.endswith("_综述.md")
                ]
            if semantic_targets:
                semantic_stats = compile_semantic_batch(
                    workspace,
                    semantic_targets,
                    progress_cb=lambda cur, tot, msg: prog("semantic", 0.45 + 0.07 * cur / max(tot, 1), msg),
                    cancelled=cancelled,
                )
                stats["semantic_documents"] = semantic_stats["documents"]
                stats["semantic_blocks"] = semantic_stats["blocks"]
                stats["semantic_extracted_blocks"] = semantic_stats["extracted_blocks"]
                stats["semantic_claims"] = semantic_stats["claims"]
                stats["semantic_failed_blocks"] = semantic_stats["failed_blocks"]
                stats["semantic_pending_documents"] = semantic_stats["pending_documents"]
                stats["semantic_failures"] = semantic_stats["failures"]
                semantic_topics = set(semantic_stats.get("affected_topics", semantic_stats["topics"])) | removed_topics
                affected_topics.update(semantic_topics)
                materialized = 0
                wiki_pages = 0
                for topic in sorted(semantic_topics):
                    try:
                        materialize_topic_state(store, topic)
                        materialized += 1
                        materialize_topic_wiki_page(store, topic)
                        wiki_pages += 1
                    except Exception as exc:
                        stats["semantic_failures"].append({"topic": topic, "error": f"TopicState: {exc}"})
                stats["semantic_topic_states"] = materialized
                stats["semantic_wiki_pages"] = wiki_pages
            elif removed_topics:
                affected_topics.update(removed_topics)
                for topic in sorted(removed_topics):
                    materialize_topic_state(store, topic)
                    materialize_topic_wiki_page(store, topic)
                stats["semantic_topic_states"] = len(removed_topics)
                stats["semantic_wiki_pages"] = len(removed_topics)
            if removed_topics:
                for kind in ("entity", "concept"):
                    try:
                        materialize_object_collection(store, kind)
                    except Exception as exc:
                        stats["semantic_failures"].append({"object_collection": kind, "error": str(exc)})
            prog(
                "semantic",
                0.52,
                f"语义编译: {stats['semantic_documents']} 篇，失败块 {stats['semantic_failed_blocks']}",
            )
            state["affected_topics"] = sorted(affected_topics)
            state["stats"] = stats
            save_ingest_state(state)
            mark_stage_done("semantic")
        if cancelled():
            raise _Cancelled()

        # 4. Index
        indexed_paths: list[str] = []
        if stage_done("index"):
            prog("index", 0.65, "跳过索引（已完成）")
        else:
            ws_path = Path(workspace)
            purged_paths = _purge_deleted_index_files(workspace)
            stats["purged_index_files"] = len(purged_paths)
            if incremental and not file_paths:
                index_targets = _scan_index_pending(workspace)
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
                    md
                    for md in ws_path.rglob("*.md")
                    if not md.name.startswith(".")
                    and "wiki" not in md.parts
                    and not md.name.endswith("_综述.md")
                    and NOTES_FOLDER in md.parts
                ]
            if index_targets:
                prog("index", 0.5, f"检查向量索引 ({len(index_targets)} 篇，仅更新有改动的)…")
                stats["indexed_files"], indexed_paths = _index_markdown_files(
                    workspace,
                    index_targets,
                    lambda cur, tot, msg: prog("index", 0.5 + 0.15 * cur / max(tot, 1), msg),
                    cancelled,
                )
            # Cross-ref only runs on files that actually changed this run.
            prog("index", 0.65, f"索引更新: {stats['indexed_files']} 篇有改动")
            state["pending_crossref_paths"] = indexed_paths
            save_ingest_state(state)
            mark_stage_done("index")
        if cancelled():
            raise _Cancelled()

        # 5. Cross-ref
        if stage_done("crossref"):
            prog("crossref", 0.7, "跳过交叉引用（已完成）")
        else:
            raw_crossref_paths = state.get("pending_crossref_paths")
            resumed_crossref_paths = (
                [str(path) for path in raw_crossref_paths] if isinstance(raw_crossref_paths, list) else []
            )
            crossref_paths = indexed_paths or resumed_crossref_paths
            # Skip cross-ref for single file (e.g. web download) — new files have no
            # meaningful vector neighbors yet, so LLM cross-ref produces poor results.
            if crossref_paths and len(crossref_paths) > 1:
                from utils.link_indexer import discover_cross_refs_for_file

                total_x = len(crossref_paths)
                # Use LLM only when few files; skip for large batches to save time
                use_llm = total_x <= 20
                cross_added = 0
                crossref_errors: list[str] = []
                for i, rel in enumerate(crossref_paths):
                    if cancelled():
                        raise _Cancelled()
                    prog(
                        "crossref",
                        0.65 + 0.05 * (i + 1) / max(total_x, 1),
                        f"交叉引用 ({i + 1}/{total_x}): {Path(rel).name}",
                    )
                    try:
                        xr = discover_cross_refs_for_file(rel, use_llm=use_llm)
                        cross_added += int(xr.get("added") or 0)
                    except Exception as e:
                        crossref_errors.append(f"{Path(rel).name}: {e}")
                stats["cross_refs"] = cross_added
                state["stats"] = stats
                save_ingest_state(state)
                if crossref_errors:
                    raise RuntimeError(f"交叉引用失败 {len(crossref_errors)} 篇: {'; '.join(crossref_errors[:3])}")
            prog("crossref", 0.7, f"交叉引用完成: {stats.get('cross_refs', 0)} 条")
            mark_stage_done("crossref")
        if cancelled():
            raise _Cancelled()

        # 6. Cascade — collect touched survey topics. The actual LLM survey work
        # runs after ingest completes so conversion/classification/indexing do not
        # block on long survey generation.
        if stage_done("cascade"):
            prog("cascade", 0.85, "跳过综述计划（已完成）")
        else:
            from sidecar.workspace_rules import load_workspace_rules, resolve_survey_topic

            rules = load_workspace_rules()
            if rules.get("auto_update_survey", True):
                resolved = {resolve_survey_topic(t, rules.get("survey_at_level", 2)) for t in affected_topics}
                cascade_topics = sorted(resolved)
            else:
                cascade_topics = []
            if cascade_topics:
                stats["cascade_topics"] = cascade_topics
                prog("cascade", 0.85, f"已安排后台综述: {len(cascade_topics)} 个主题")
            else:
                prog("cascade", 0.85, "无需更新综述")

            mark_stage_done("cascade")
        if cancelled():
            raise _Cancelled()

        # 7. Lint
        if stage_done("lint"):
            prog("lint", 0.92, "跳过健康检查（已完成）")
        else:
            from sidecar.kb_lint import log_lint_report, run_kb_lint

            prog("lint", 0.88, "检查断链、孤儿页、过时综述…")
            lint_report = run_kb_lint(workspace)
            lint_summary = lint_report.get("summary", {})
            stats["lint"] = lint_summary if isinstance(lint_summary, dict) else {}
            log_lint_report(lint_report)
            lint_total = stats["lint"].get("total", 0)
            prog("lint", 0.92, f"Lint 完成: {lint_total} 项")
            mark_stage_done("lint")
        if cancelled():
            raise _Cancelled()

        # 8. Sync wiki
        if stage_done("sync"):
            prog("sync", 1.0, "跳过同步（已完成）")
        else:
            prog("sync", 0.95, "同步 WIKI.md…")
            sync_wiki_with_files()
            mark_stage_done("sync")

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

    except _Cancelled:
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


class _Cancelled(Exception):
    pass
