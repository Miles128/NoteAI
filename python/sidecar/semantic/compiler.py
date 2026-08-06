"""Phase 1 semantic compiler entry point."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sidecar.semantic.ids import content_hash, stable_id
from sidecar.semantic.parser import parse_semantic_blocks
from sidecar.semantic.store import SCHEMA_VERSION, SemanticStore
from utils.text_utils import parse_frontmatter

COMPILER_VERSION = 1


def _relative_note_path(workspace: Path, file_path: str | Path) -> tuple[Path, str]:
    full = Path(file_path)
    if not full.is_absolute():
        full = workspace / full
    full = full.resolve()
    try:
        relative = full.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError("语义编译只允许处理当前工作区内的文件") from exc
    if full.suffix.lower() != ".md" or "Notes" not in relative.parts:
        raise ValueError("语义编译只处理 Notes/ 下的 Markdown 文件")
    return full, relative.as_posix()


def _write_manifest(store: SemanticStore, payload: dict) -> None:
    path = store.root / "manifest.json"
    _prompt_version: int | None
    try:
        from sidecar.semantic.extractor import PROMPT_VERSION as _prompt_version
    except Exception:
        _prompt_version = None
    payload.setdefault("prompt_version", _prompt_version)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, temp_path = tempfile.mkstemp(dir=store.root, prefix=".manifest.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def compile_note_semantics(workspace: str | Path, file_path: str | Path) -> dict:
    """Parse one source note into an idempotent document/block snapshot."""
    workspace_path = Path(workspace).resolve()
    full, relative = _relative_note_path(workspace_path, file_path)
    if not full.exists():
        return {"success": False, "file": relative, "message": "文件不存在"}

    raw = full.read_text(encoding="utf-8")
    digest = content_hash(raw)
    document_id = stable_id("doc", relative)
    store = SemanticStore(workspace_path)
    store.initialize()
    previous = store.document(relative)
    previous_objects = store.objects_for_document(document_id)
    if previous is not None and previous["content_hash"] == digest:
        return {
            "success": True,
            "skipped": True,
            "file": relative,
            "document_id": document_id,
            "blocks": len(store.blocks_for_document(document_id)),
            "affected_topics": [],
            "affected_objects": previous_objects,
        }

    meta, _ = parse_frontmatter(raw)
    meta = meta or {}
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [item.strip() for item in tags.split(",") if item.strip()]
    if not isinstance(tags, list):
        tags = []
    blocks = parse_semantic_blocks(document_id, raw)
    now = datetime.now(timezone.utc).isoformat()
    store.replace_document(
        document={
            "id": document_id,
            "path": relative,
            "content_hash": digest,
            "title": str(meta.get("title") or full.stem),
            "topic": str(meta.get("topic") or ""),
            "tags_json": json.dumps(tags, ensure_ascii=False),
            "status": "parsed",
            "compiled_at": now,
        },
        blocks=blocks,
    )
    _write_manifest(
        store,
        {
            "compiler_version": COMPILER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "last_success_at": now,
        },
    )
    return {
        "success": True,
        "skipped": False,
        "file": relative,
        "document_id": document_id,
        "blocks": len(blocks),
        "affected_topics": sorted(
            {
                topic
                for topic in (
                    str(previous["topic"]) if previous is not None else "",
                    str(meta.get("topic") or ""),
                )
                if topic
            }
        ),
        "affected_objects": previous_objects,
    }


def compile_semantic_batch(
    workspace: str | Path,
    file_paths: Sequence[str | Path],
    *,
    extract: bool = True,
    claims_only: bool = False,
    progress_cb=None,
    cancelled=None,
) -> dict:
    """Compile a note batch; semantic failures are reported per file."""
    from sidecar.semantic.extractor import extract_document_semantics

    store = SemanticStore(workspace)
    stats: dict[str, Any] = {
        "documents": 0,
        "blocks": 0,
        "extracted_blocks": 0,
        "claims": 0,
        "rejected_claims": 0,
        "failed_blocks": 0,
        "pending_documents": 0,
        "topics": set(),
        "affected_topics": set(),
        "noise_cleanup": {"entities": 0, "concepts": 0},
        "merge_duplicates": {"merged_groups": 0, "merged_entities": 0},
        "purge_orphans": {"entities": 0, "concepts": 0},
        "deactivate_orphans": {"entities": 0, "concepts": 0},
        "delete_inactive": {"entities": 0, "concepts": 0},
        "failures": [],
    }
    total = len(file_paths)
    compiled_documents: list[dict] = []

    # Deactivate legacy deterministic noise (file names, flag tokens, merged
    # A/B names) written before the extraction gate existed. Idempotent and
    # cheap; new noise is already rejected in extractor validation.
    try:
        stats["noise_cleanup"] = store.deactivate_noise_objects()
    except Exception as exc:
        stats["failures"].append({"file": "<noise-cleanup>", "error": str(exc)})

    # Merge duplicate entities with the same name (legacy data from before the
    # ID generation was fixed to use name-only). Idempotent.
    try:
        stats["merge_duplicates"] = store.merge_duplicate_entities()
    except Exception as exc:
        stats["failures"].append({"file": "<merge-duplicates>", "error": str(exc)})

    # Purge orphan and mundane objects (isolated + low confidence + short name).
    try:
        stats["purge_orphans"] = store.purge_orphan_objects()
    except Exception as exc:
        stats["failures"].append({"file": "<purge-orphans>", "error": str(exc)})

    # Deactivate objects with zero source mentions (no traceable evidence).
    try:
        stats["deactivate_orphans"] = store.deactivate_orphan_objects()
    except Exception as exc:
        stats["failures"].append({"file": "<deactivate-orphans>", "error": str(exc)})

    # Permanently remove deactivated rows (audit lives in the change log).
    try:
        stats["delete_inactive"] = store.delete_inactive_objects()
    except Exception as exc:
        stats["failures"].append({"file": "<delete-inactive>", "error": str(exc)})

    # Phase A is deterministic and fast: snapshot every source document first.
    # This makes full-library coverage visible immediately even while LLM
    # extraction is still running.
    for index, file_path in enumerate(file_paths):
        if cancelled and cancelled():
            break
        if progress_cb:
            progress_cb(index + 1, total, f"语义解析 ({index + 1}/{total}): {Path(file_path).name}")
        try:
            compiled = compile_note_semantics(workspace, file_path)
            if not compiled.get("success"):
                raise RuntimeError(compiled.get("message") or "语义解析失败")
            stats["documents"] += 1
            stats["blocks"] += int(compiled.get("blocks") or 0)
            document = store.document(compiled["file"])
            if document is not None and document["topic"]:
                stats["topics"].add(document["topic"])
            stats["affected_topics"].update(compiled.get("affected_topics") or [])
            compiled_documents.append(
                {
                    "file": compiled["file"],
                    "document_id": compiled["document_id"],
                    "previous_objects": compiled.get("affected_objects") or [],
                }
            )
        except Exception as exc:
            stats["failures"].append({"file": str(file_path), "error": str(exc)})

    # Phase B uses the existing global four-call LLM semaphore. The old
    # document-by-document loop left three slots idle and made a full build take
    # many hours. Each worker uses independent SQLite connections.
    if extract and compiled_documents and not (cancelled and cancelled()):
        worker_count = min(4, len(compiled_documents))

        def extract_one(document_id: str) -> dict:
            return extract_document_semantics(SemanticStore(workspace), document_id, claims_only=claims_only)

        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="semantic-extract") as pool:
            futures = {pool.submit(extract_one, item["document_id"]): item["file"] for item in compiled_documents}
            for completed, future in enumerate(as_completed(futures), start=1):
                file_name = futures[future]
                if progress_cb:
                    progress_cb(
                        completed,
                        len(compiled_documents),
                        f"语义抽取 ({completed}/{len(compiled_documents)}): {Path(file_name).name}",
                    )
                try:
                    semantic = future.result()
                    stats["extracted_blocks"] += int(semantic.get("extracted") or 0)
                    stats["claims"] += int(semantic.get("claims") or 0)
                    stats["rejected_claims"] += int(semantic.get("rejected_claims") or 0)
                    stats["failed_blocks"] += int(semantic.get("failed") or 0)
                    if semantic.get("pending"):
                        stats["pending_documents"] += 1
                    if semantic.get("failures"):
                        stats["failures"].append({"file": file_name, "blocks": semantic["failures"]})
                except Exception as exc:
                    stats["failures"].append({"file": file_name, "error": str(exc)})
                if cancelled and cancelled():
                    for pending in futures:
                        pending.cancel()
                    break
    # Semantic pages are derived views, not another user task.  Refresh just
    # the documents processed in this run after all extraction transactions
    # have settled, so concurrent block workers never fight page generation.
    if extract and compiled_documents and not (cancelled and cancelled()):
        from sidecar.semantic.materializer import materialize_documents

        materialized = materialize_documents(
            store,
            {item["document_id"] for item in compiled_documents},
            previous_objects=[obj for item in compiled_documents for obj in item["previous_objects"]],
            affected_topics=set(stats["affected_topics"]),
            include_objects=not claims_only,
        )
        stats["materialized"] = materialized
        stats["failures"].extend({"materialization": failure} for failure in materialized["failures"])
    else:
        stats["materialized"] = {
            "entities": 0,
            "concepts": 0,
            "topics": 0,
            "removed": {"entities": 0, "concepts": 0},
            "failures": [],
        }
    # Structured conflict detection is a derived view over the fresh claim
    # snapshot; rerun it after extraction settles so the Conflicts tab always
    # reflects the latest conclusions.
    if extract and compiled_documents and not (cancelled and cancelled()):
        try:
            from sidecar.semantic.conflict_detector import scan_and_persist

            stats["conflicts"] = scan_and_persist(store)
        except Exception as exc:
            stats["failures"].append({"conflict_scan": str(exc)})
    stats["topics"] = sorted(stats["topics"])
    stats["affected_topics"] = sorted(stats["affected_topics"])
    return stats


def retry_failed_blocks(
    store: SemanticStore,
    *,
    claims_only: bool,
    limit: int,
) -> dict:
    """重试抽取失败的块（claim_extractions / block_extractions 中 status='failed'）。

    失败块不会被 is_current 跳过（is_current 只认 'complete'），因此直接对
    失败块所属文档重新抽取即可；成功后会写回 complete 状态。同步执行并
    限制单次数量，避免 API 长时间不可用时一次重试上千块阻塞 sidecar。
    """
    table = "claim_extractions" if claims_only else "block_extractions"
    with store.connect() as conn:
        failed = conn.execute(
            f"""SELECT ce.block_id, ce.error, b.document_id
                FROM {table} ce JOIN blocks b ON b.id = ce.block_id
                WHERE ce.status = 'failed'
                ORDER BY ce.extracted_at
                LIMIT ?""",
            (limit,),
        ).fetchall()
    if not failed:
        return {"success": True, "failed_blocks": 0, "documents": 0, "extracted_blocks": 0, "failures": []}
    # 同一文档的多个失败块一次抽取即可覆盖；失败块数量通常远小于文档数。
    doc_ids = sorted({row["document_id"] for row in failed})
    from sidecar.semantic.extractor import extract_document_semantics

    def extract_one(doc_id: str) -> dict:
        try:
            return extract_document_semantics(store, doc_id, claims_only=claims_only)
        except Exception as exc:  # 抽取器内部异常也归为失败，不让单文档拖垮整批
            return {
                "success": False,
                "extracted": 0,
                "claims": 0,
                "failures": [{"block_id": None, "error": str(exc)}],
            }

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(doc_ids)), thread_name_prefix="semantic-retry") as pool:
        futures = {pool.submit(extract_one, doc_id): doc_id for doc_id in doc_ids}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    extracted = sum(int(result.get("extracted") or 0) for result in results.values())
    failures = []
    seen_failures: set[tuple[str, str]] = set()
    for doc_id in doc_ids:
        result = results[doc_id]
        for failure in result.get("failures") or []:
            key = (doc_id, failure.get("error") or "")
            if key not in seen_failures:
                seen_failures.add(key)
                failures.append({"document_id": doc_id, "error": key[1]})
    with store.connect() as conn:
        remaining = conn.execute(
            f"SELECT count(*) FROM {table} ce JOIN blocks b ON b.id = ce.block_id WHERE ce.status = 'failed'"
        ).fetchone()[0]
    return {
        "success": True,
        "failed_blocks": len(failed),
        "documents": len(doc_ids),
        "extracted_blocks": extracted,
        "remaining_failed": remaining,
        "failures": failures[:20],
    }


def run_full_compile(
    workspace: str | Path,
    paths: Sequence[str | Path],
    *,
    claims_only: bool = False,
    progress_cb=None,
    done_cb=None,
) -> None:
    """全库语义编译的完整流程：清理失联文档 → 批量编译 → 重建聚合页/主题页。

    ``progress_cb(progress, message, metadata)`` 汇报中间进度，
    ``done_cb(message, metadata)`` 汇报最终结果；任务状态推送由调用方
    （handler 的 job 通道）负责，本函数不感知 job 体系。
    """
    from sidecar.semantic.object_wiki import materialize_object_collection
    from sidecar.semantic.topic_state import materialize_topic_state
    from sidecar.semantic.wiki import materialize_topic_wiki_page

    total = max(len(paths), 1)
    store = SemanticStore(workspace)
    # keep_paths=paths：同时清理磁盘上已不存在、以及不在本次编译集合内
    # （如隐藏目录中的残留文档）的记录，保证工作台计数与源文档一致。
    removed_topics = set(store.purge_missing_documents(keep_paths=paths))

    def progress(current, _total, message):
        if progress_cb:
            progress_cb(
                current / total,
                message,
                {"processed_documents": current, "total_documents": len(paths)},
            )

    stats = compile_semantic_batch(workspace, paths, progress_cb=progress, claims_only=claims_only)
    cleanup_failures = []
    if not claims_only:
        for kind in ("entity", "concept"):
            try:
                materialize_object_collection(store, kind)
            except (OSError, ValueError, sqlite3.Error) as exc:
                cleanup_failures.append({"kind": f"{kind}_collection", "error": str(exc)})
    for topic in sorted(removed_topics):
        try:
            materialize_topic_state(store, topic)
            materialize_topic_wiki_page(store, topic)
        except (OSError, ValueError, sqlite3.Error) as exc:
            cleanup_failures.append({"kind": "removed_topic", "topic": topic, "error": str(exc)})
    if cleanup_failures:
        stats["failures"].extend({"cleanup": item} for item in cleanup_failures)
    materialized = stats.get("materialized", {})
    if claims_only:
        message = (
            f"全库命题编译完成：{stats['documents']} 篇，"
            f"命题 {stats['claims']} 条（拒绝 {stats['rejected_claims']}），失败块 {stats['failed_blocks']}"
        )
    else:
        materialized_message = (
            f"；已自动更新实体聚合页（涉及 {materialized.get('entities', 0)} 条）、"
            f"概念聚合页（涉及 {materialized.get('concepts', 0)} 条）、"
            f"主题页 {materialized.get('topics', 0)}"
        )
        message = f"全库语义编译完成：{stats['documents']} 篇，失败块 {stats['failed_blocks']}{materialized_message}"
    if done_cb:
        done_cb(
            message,
            {
                "processed_documents": stats["documents"],
                "total_documents": len(paths),
                "blocks": stats["blocks"],
                "claims": stats["claims"],
                "rejected_claims": stats["rejected_claims"],
                "failed_blocks": stats["failed_blocks"],
                "pending_documents": stats["pending_documents"],
                "failure_count": len(stats["failures"]),
                "removed_topics": sorted(removed_topics),
                "materialized": materialized,
            },
        )
