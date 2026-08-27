"""RAG index write path: build, add, replace, delete."""

from __future__ import annotations

import gc
import shutil
import time
import uuid
from typing import Any

import bm25s
import zvec

from sidecar.rag.index_bm25 import _bm25_corpus_from_retriever, _build_and_save_bm25, rebuild_search_indices
from sidecar.rag.index_core import (
    _COLLECTION_CACHE,
    _COLLECTION_CACHE_LOCK,
    _COLLECTION_IO_LOCK,
    _INDEX_BATCH_SIZE,
    _bm25s_dir,
    _build_schema,
    _bump_manifest_version,
    _chunk_to_doc,
    _collection_lock_error,
    _collection_path,
    _delete_ids_batched,
    _empty_metadata,
    _escape_filter_value,
    _get_collection,
    _is_zvec_lock_error,
    _load_metadata,
    _normalize_workspace,
    _rag_index_dir,
    _release_collection,
    _save_metadata,
    _tags_from_fields,
    _update_metadata_index,
    _write_docs_batched,
    clear_collection_cache,
    load_manifest,
    save_manifest,
)
from utils.logger import logger


def build_index(workspace: str, chunks: list[dict], embeddings: list[dict], progress_callback=None) -> dict[str, Any]:
    ws = _normalize_workspace(workspace)
    index_dir = _rag_index_dir(ws)
    index_dir.mkdir(parents=True, exist_ok=True)

    with _COLLECTION_IO_LOCK:
        collection_path = _collection_path(ws)
        staging_path = collection_path.with_name(f"{collection_path.name}.building-{uuid.uuid4().hex}")
        backup_path = collection_path.with_name(f"{collection_path.name}.backup-{uuid.uuid4().hex}")
        shutil.rmtree(staging_path, ignore_errors=True)
        shutil.rmtree(backup_path, ignore_errors=True)
        for old in index_dir.glob("*.tmp"):
            old.unlink()

        last_err: Exception | None = None
        collection = None
        for attempt in range(3):
            try:
                collection = zvec.create_and_open(str(staging_path), _build_schema())
                break
            except Exception as e:
                last_err = e
                if not _is_zvec_lock_error(e):
                    raise
                gc.collect()
                time.sleep(0.08 * (attempt + 1))
        if collection is None:
            raise _collection_lock_error(ws) from last_err

        batch_size = _INDEX_BATCH_SIZE
        total = len(chunks)

        for i in range(0, total, batch_size):
            batch_chunks = chunks[i : i + batch_size]
            batch_embeds = embeddings[i : i + batch_size]
            docs = [_chunk_to_doc(c, e) for c, e in zip(batch_chunks, batch_embeds, strict=False)]
            if docs:
                collection.insert(docs)
            if progress_callback:
                progress_callback(min(i + batch_size, total), total, "写入索引")

        collection.flush()

        # Publish the completed vector collection atomically. The previous
        # generation remains available until every zvec batch has succeeded.
        collection = None
        gc.collect()
        _release_collection(ws)
        if collection_path.exists():
            collection_path.rename(backup_path)
        try:
            staging_path.rename(collection_path)
            collection = zvec.open(str(collection_path))
        except Exception:
            shutil.rmtree(collection_path, ignore_errors=True)
            if backup_path.exists():
                backup_path.rename(collection_path)
            raise
        finally:
            shutil.rmtree(staging_path, ignore_errors=True)

        with _COLLECTION_CACHE_LOCK:
            _COLLECTION_CACHE[ws] = collection
        shutil.rmtree(backup_path, ignore_errors=True)

        # Build BM25s index
        if progress_callback:
            progress_callback(total, total, "构建 BM25 索引...")

        _build_and_save_bm25(chunks, _bm25s_dir(ws), ws)

        # Build metadata indices
        metadata = _empty_metadata()
        for chunk in chunks:
            _update_metadata_index(metadata, chunk, mode="add")
        _save_metadata(ws, metadata)

        _bump_manifest_version(ws)

    return {"success": True, "chunk_count": total, "_collection": collection}


def add_chunks(
    workspace: str,
    chunks: list[dict],
    embeddings: list[dict],
    *,
    rebuild_bm25s: bool = True,
) -> None:
    if not chunks:
        return

    with _COLLECTION_IO_LOCK:
        collection = _get_collection(workspace)
        metadata = _load_metadata(workspace)

        docs = []
        for chunk, emb in zip(chunks, embeddings, strict=False):
            if not chunk.get("id"):
                continue
            docs.append(_chunk_to_doc(chunk, emb))
            _update_metadata_index(metadata, chunk, mode="add")

        if not docs:
            return

        _write_docs_batched(collection, docs)
        collection.flush()
        _save_metadata(workspace, metadata)

    # Rebuild BM25s with merged corpus
    if not rebuild_bm25s:
        return
    try:
        bm25_dir = _bm25s_dir(workspace)
        if bm25_dir.exists() and any(bm25_dir.iterdir()):
            old_retriever = bm25s.BM25.load(bm25_dir, load_corpus=True)
            old_corpus = _bm25_corpus_from_retriever(old_retriever)
        else:
            old_corpus = []

        old_map = {c.get("id"): c for c in old_corpus if c.get("id")}
        for c in chunks:
            if c.get("id"):
                old_map[c["id"]] = c
        merged_corpus = list(old_map.values())

        _build_and_save_bm25(merged_corpus, bm25_dir, workspace)
    except Exception as e:
        logger.warning(f"[rag/index] BM25s rebuild failed: {e}\n")


def replace_file_chunks(workspace: str, replacements: dict[str, dict]) -> int:
    """Atomically-ish replace chunks for multiple files under one writer lock.

    New documents are upserted before stale ids are removed, so a failed write
    leaves the previous searchable generation intact. Manifest, metadata and
    BM25 are committed only after the zvec mutation succeeds.
    """
    if not replacements:
        return 0

    with _COLLECTION_IO_LOCK:
        collection = _get_collection(workspace)
        manifest = load_manifest(workspace)
        manifest_files = manifest.setdefault("files", {})
        docs: list[zvec.Doc] = []
        stale_ids: list[str] = []

        for rel_path, payload in replacements.items():
            chunks = payload.get("chunks") or []
            embeddings = payload.get("embeddings") or []
            new_ids = {str(chunk.get("id")) for chunk in chunks if chunk.get("id")}
            old_ids = set((manifest_files.get(rel_path) or {}).get("chunks") or [])
            stale_ids.extend(sorted(old_ids - new_ids))
            docs.extend(
                _chunk_to_doc(chunk, embedding)
                for chunk, embedding in zip(chunks, embeddings, strict=False)
                if chunk.get("id")
            )

        if docs:
            _write_docs_batched(collection, docs)
            collection.flush()
        if stale_ids:
            _delete_ids_batched(collection, stale_ids)
            collection.flush()

        for rel_path, payload in replacements.items():
            chunks = payload.get("chunks") or []
            manifest_files[rel_path] = {
                "mtime": payload.get("mtime", 0),
                "size": payload.get("size", 0),
                "chunks": [chunk["id"] for chunk in chunks if chunk.get("id")],
            }

        all_chunk_ids = [chunk_id for entry in manifest_files.values() for chunk_id in (entry.get("chunks") or [])]
        indexed_count = rebuild_search_indices(
            workspace,
            all_chunk_ids,
            collection=collection,
        )
        save_manifest(workspace, manifest)
        return indexed_count


def delete_by_file(
    workspace: str,
    file_path: str,
    collection: zvec.Collection | None = None,
    *,
    rebuild_bm25s: bool = True,
) -> list[dict]:
    """Delete all chunks belonging to a file.

    Args:
        workspace: target workspace.
        file_path: relative file path stored in chunk metadata.
        collection: optional opened zvec collection; if omitted, one is fetched.
        rebuild_bm25s: when False, skip BM25s rebuild (callers that batch deletes
            should rebuild once at the end).

    Returns:
        List of removed chunk dicts.
    """
    with _COLLECTION_IO_LOCK:
        if collection is None:
            collection = _get_collection(workspace)
        metadata = _load_metadata(workspace)

        removed = _delete_file_chunks(collection, metadata, file_path, workspace)

        if removed:
            collection.flush()

        _save_metadata(workspace, metadata)

    # Rebuild BM25s without deleted docs
    if not rebuild_bm25s:
        return removed

    try:
        bm25_dir = _bm25s_dir(workspace)
        if not bm25_dir.exists() or not any(bm25_dir.iterdir()):
            return removed
        retriever = bm25s.BM25.load(bm25_dir, load_corpus=True)
        old_corpus = _bm25_corpus_from_retriever(retriever)
        removed_ids = {c["id"] for c in removed}
        new_corpus = [c for c in old_corpus if c.get("id") not in removed_ids]
        _build_and_save_bm25(new_corpus, bm25_dir, workspace)
        manifest = load_manifest(workspace)
        manifest.get("files", {}).pop(file_path, None)
        save_manifest(workspace, manifest)
    except Exception as e:
        logger.warning(f"[rag/index] BM25s rebuild after delete failed: {e}\n")

    return removed


def _delete_file_chunks(
    collection: zvec.Collection,
    metadata: dict[str, Any],
    file_path: str,
    workspace: str,
) -> list[dict]:
    """Query and delete all chunks of one file from a zvec collection.

    Mutates ``metadata`` inverted indices in place; caller persists afterwards.
    """
    removed: list[dict] = []
    try:
        filter_expr = f"file_path = {_escape_filter_value(file_path)}"
        docs = collection.query(
            filter=filter_expr,
            topk=10000,
            output_fields=["content", "file_path", "topic", "tags_json", "section_title"],
        )
        for doc in docs:
            fields = doc.fields or {}
            chunk = {
                "id": doc.id,
                "content": fields.get("content", ""),
                "file_path": fields.get("file_path", ""),
                "topic": fields.get("topic", ""),
                "tags": _tags_from_fields(fields),
                "section_title": fields.get("section_title", ""),
            }
            removed.append(chunk)
            _update_metadata_index(metadata, chunk, mode="remove")
    except Exception as e:
        logger.warning(f"[rag/index] zvec delete query failed: {e}\n")
        # Collection object may be in an inconsistent state; drop it from cache.
        clear_collection_cache(workspace)
        raise

    if removed:
        _delete_ids_batched(collection, [c["id"] for c in removed])
    return removed


def delete_files_batched(workspace: str, file_paths: list[str]) -> list[dict]:
    """Delete chunks of multiple files under one writer lock.

    BM25 is rebuilt exactly once at the end instead of once per file —
    deleting K files previously triggered K full corpus rebuilds.
    """
    if not file_paths:
        return []
    removed_all: list[dict] = []
    with _COLLECTION_IO_LOCK:
        collection = _get_collection(workspace)
        metadata = _load_metadata(workspace)
        for file_path in file_paths:
            removed_all.extend(_delete_file_chunks(collection, metadata, file_path, workspace))
        if removed_all:
            collection.flush()
        _save_metadata(workspace, metadata)

    if removed_all:
        try:
            bm25_dir = _bm25s_dir(workspace)
            if bm25_dir.exists() and any(bm25_dir.iterdir()):
                retriever = bm25s.BM25.load(bm25_dir, load_corpus=True)
                old_corpus = _bm25_corpus_from_retriever(retriever)
                removed_ids = {c["id"] for c in removed_all}
                new_corpus = [c for c in old_corpus if c.get("id") not in removed_ids]
                _build_and_save_bm25(new_corpus, bm25_dir, workspace)
            manifest = load_manifest(workspace)
            files_manifest = manifest.setdefault("files", {})
            for file_path in file_paths:
                files_manifest.pop(file_path, None)
            save_manifest(workspace, manifest)
        except Exception as e:
            logger.warning(f"[rag/index] BM25s rebuild after batch delete failed: {e}\n")

    return removed_all
