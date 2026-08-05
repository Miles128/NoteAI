"""Phase 1 semantic compiler entry point."""

from __future__ import annotations

import json
import os
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
        "failed_blocks": 0,
        "pending_documents": 0,
        "topics": set(),
        "affected_topics": set(),
        "failures": [],
    }
    total = len(file_paths)
    compiled_documents: list[dict] = []

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
