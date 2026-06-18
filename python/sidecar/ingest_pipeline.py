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

STAGES = ("schema", "convert", "compile", "classify", "index", "crossref", "cascade", "lint", "sync")

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

    state = normalize_ingest_state()
    status = state.get("status", "idle")

    if needs_schema_setup(ws):
        return {"action": "none", "needs_schema": True}

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
        if md.name.startswith(".") or "wiki" in md.parts:
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
) -> tuple[int, list[str]]:
    if not config.rag_enabled:
        return 0, []

    from sidecar.rag.chunker import chunk_file
    from sidecar.rag.embedder import encode_documents
    from sidecar.rag.index import add_chunks, delete_by_file
    from sidecar.rag.index_state import file_needs_index, mark_indexed

    indexed = 0
    indexed_paths: list[str] = []
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
            indexed_paths.append(rel)
        except Exception:
            continue
    return indexed, indexed_paths


def run_ingest(
    mode: str = "full",
    file_paths: list[str] | None = None,
    send_progress: Callable[[str, float, str, dict | None], None] | None = None,
    send_event: Callable[[dict], None] | None = None,
    *,
    resume: bool = False,
) -> dict:
    """
    Run ingest pipeline. *send_progress(stage, progress 0-1, message, extra)*.
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    clear_cancel()
    prev = load_ingest_state() if resume else {}
    stats = {
        "converted": 0,
        "compiled": 0,
        "classified": 0,
        "pending_topics": 0,
        "indexed_files": 0,
        "cascade_updated": 0,
        "cascade_failed": [],
    }
    if resume and isinstance(prev.get("stats"), dict):
        stats.update({k: prev["stats"].get(k, v) for k, v in stats.items() if k in prev["stats"]})

    if prev.get("force_full_next"):
        mode = "full"
        resume = False

    state = {
        "status": "running",
        "mode": mode,
        "stage": "schema",
        "started_at": time.time(),
        "stats": stats,
        "file_paths": list(file_paths or []),
        "resume": resume,
    }
    state.pop("force_full_next", None)
    if resume and prev.get("completed_stages"):
        state["completed_stages"] = list(prev["completed_stages"])
    save_ingest_state(state)

    completed_stages: set[str] = set(state.get("completed_stages") or [])

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

    affected_topics: set[str] = set()

    try:
        ensure_schema(workspace)
        if needs_schema_setup(workspace):
            state["status"] = "needs_schema"
            save_ingest_state(state)
            if send_event:
                send_event(
                    {
                        "id": "event",
                        "result": {
                            "type": "ingest_complete",
                            "success": False,
                            "needs_schema": True,
                            "message": "请先完成工作区 Schema 配置",
                        },
                    }
                )
            return {"success": False, "needs_schema": True, "message": "请先完成工作区 Schema 配置"}

        prog("schema", 0.02, "schema.md 已就绪…")
        mark_stage_done("schema")
        if is_cancelled():
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
                results = conv.convert_batch(pending_files, workspace, raw_path=raw_path)
                stats["converted"] = sum(1 for r in results if r.get("success"))
                for r in results:
                    if r.get("success") and r.get("output_path"):
                        out = Path(r["output_path"])
                        try:
                            converted_note_paths.append(str(out.relative_to(workspace)))
                        except ValueError:
                            converted_note_paths.append(r["output_path"])
            prog("convert", 0.16, f"转换完成: {stats['converted']} 个")
            mark_stage_done("convert")
        else:
            prog("convert", 0.16, "无需转换")
            mark_stage_done("convert")
        if is_cancelled():
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
        if is_cancelled():
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
            for i, md in enumerate(to_classify):
                if is_cancelled():
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
                except Exception:
                    continue
            prog("classify", 0.45, f"分类完成: {stats['classified']} 篇，待确认 {stats['pending_topics']}")
            mark_stage_done("classify")
        if is_cancelled():
            raise _Cancelled()

        # 4. Index
        indexed_paths: list[str] = []
        if stage_done("index"):
            prog("index", 0.65, "跳过索引（已完成）")
        else:
            ws_path = Path(workspace)
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
                )
            # Cross-ref should cover all classified files, not just RAG-indexed ones
            if not indexed_paths:
                indexed_paths = [
                    str(md.relative_to(workspace))
                    for md in ws_path.rglob("*.md")
                    if not md.name.startswith(".")
                    and "wiki" not in md.parts
                    and not md.name.endswith("_综述.md")
                    and not md.name.endswith("综述.md")
                    and NOTES_FOLDER in md.parts
                ]
            prog("index", 0.65, f"索引更新: {stats['indexed_files']} 篇有改动")
            state["pending_crossref_paths"] = indexed_paths
            save_ingest_state(state)
            mark_stage_done("index")
        if is_cancelled():
            raise _Cancelled()

        # 5. Cross-ref
        if stage_done("crossref"):
            prog("crossref", 0.7, "跳过交叉引用（已完成）")
        else:
            crossref_paths = indexed_paths or state.get("pending_crossref_paths") or []
            if crossref_paths:
                from utils.link_indexer import discover_cross_refs_for_file

                total_x = len(crossref_paths)
                # Use LLM only when few files; skip for large batches to save time
                use_llm = total_x <= 20
                cross_added = 0
                for i, rel in enumerate(crossref_paths):
                    if is_cancelled():
                        raise _Cancelled()
                    prog(
                        "crossref",
                        0.65 + 0.05 * (i + 1) / max(total_x, 1),
                        f"交叉引用 ({i + 1}/{total_x}): {Path(rel).name}",
                    )
                    try:
                        xr = discover_cross_refs_for_file(rel, use_llm=use_llm)
                        cross_added += int(xr.get("added") or 0)
                    except Exception:
                        continue
                stats["cross_refs"] = cross_added
            prog("crossref", 0.7, f"交叉引用完成: {stats.get('cross_refs', 0)} 条")
            mark_stage_done("crossref")
        if is_cancelled():
            raise _Cancelled()

        # 6. Cascade — only topics touched this run (+ prior failures via retry)
        if stage_done("cascade"):
            prog("cascade", 0.85, "跳过综述（已完成）")
        else:
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

            if not is_cancelled():
                retry_result = retry_failed_cascades(send_response=send_event)
                stats["cascade_updated"] += retry_result.get("updated", 0)
            mark_stage_done("cascade")
        if is_cancelled():
            raise _Cancelled()

        # 7. Lint
        if stage_done("lint"):
            prog("lint", 0.92, "跳过健康检查（已完成）")
        else:
            from sidecar.kb_lint import log_lint_report, run_kb_lint

            prog("lint", 0.88, "检查断链、孤儿页、过时综述…")
            lint_report = run_kb_lint(workspace)
            stats["lint"] = lint_report.get("summary", {})
            log_lint_report(lint_report)
            lint_total = stats["lint"].get("total", 0)
            prog("lint", 0.92, f"Lint 完成: {lint_total} 项")
            mark_stage_done("lint")
        if is_cancelled():
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
        state.pop("error", None)
        save_ingest_state(state)
        prog("sync", 1.0, "入库流水线完成")

        if send_event:
            send_event(
                {
                    "id": "event",
                    "result": {
                        "type": "ingest_complete",
                        "success": True,
                        "stats": stats,
                    },
                }
            )
        return {"success": True, "stats": stats}

    except _Cancelled:
        state["status"] = "cancelled"
        save_ingest_state(state)
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
