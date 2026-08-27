"""RAG index stats and hybrid (dense + BM25) search."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import zvec

from sidecar.rag.index_bm25 import _normalize_sparse_scores, _sparse_search, ensure_bm25_index
from sidecar.rag.index_core import (
    _COLLECTION_IO_LOCK,
    _doc_to_result,
    _escape_filter_value,
    _get_collection,
    _load_metadata,
    filter_usable_chunks,
)
from sidecar.rag.rag_config import hybrid_weights
from utils.error_handler import log_exception
from utils.logger import logger

_HYBRID_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag_hybrid")
_DENSE_EF_CAP = 128
_DENSE_EF_MULTIPLIER = 8


def count_indexed_chunks(workspace: str, *, allow_metadata_fallback: bool = True) -> int:
    """Return approximate chunk count from the metadata inverted index.

    Cross-checks the actual collection count when available and falls back to
    metadata when the collection is empty or inaccessible.
    """
    metadata = _load_metadata(workspace)
    files = metadata.get("files") or {}
    metadata_total = 0
    for ids in files.values():
        metadata_total += len(ids)

    collection_count = _collection_count(workspace)

    if collection_count < 0 and not allow_metadata_fallback:
        return -1

    if collection_count >= 0 and metadata_total != collection_count:
        logger.warning(
            f"Chunk count mismatch: metadata={metadata_total}, collection={collection_count}; using collection count"
        )
        return collection_count
    return metadata_total


def _collection_count(workspace: str) -> int:
    """Query the zvec collection for total entity count, or -1 if unavailable."""
    # Status endpoints must not queue behind a long full rebuild. The previous
    # behavior occupied every RPC worker while build_index held this lock.
    if not _COLLECTION_IO_LOCK.acquire(blocking=False):
        return -1
    try:
        return int(_get_collection(workspace).stats.doc_count)
    except Exception as e:
        log_exception("[rag/index] failed to query collection count", e, level="debug", logger=logger)
        return -1
    finally:
        _COLLECTION_IO_LOCK.release()


def _dense_search(
    collection: zvec.Collection,
    query_dense: list[float],
    candidate_ids: set[str] | None,
    top_k: int,
) -> list[dict]:
    if candidate_ids is not None and not candidate_ids:
        return []

    query = zvec.Query(
        field_name="dense",
        vector=query_dense,
        param=zvec.HnswQueryParam(ef=min(top_k * _DENSE_EF_MULTIPLIER, _DENSE_EF_CAP)),
    )

    # zvec filters do not operate on the primary id.  Query a larger pool and
    # post-filter manually when candidate_ids is provided.
    search_topk = top_k * 4
    if candidate_ids:
        search_topk = max(search_topk, min(len(candidate_ids), 10000))

    docs = collection.query(
        query,
        topk=search_topk,
        output_fields=["content", "file_path", "topic", "tags_json", "section_title"],
        include_vector=True,
    )

    results = []
    for doc in docs:
        if candidate_ids is not None and doc.id not in candidate_ids:
            continue
        # zvec cosine distance -> similarity score
        score = 1.0 - (doc.score or 0.0)
        r = _doc_to_result(doc, score)
        results.append(r)
    return results


def _filter_candidates(
    workspace: str,
    topics: list[str] | None,
    tags: list[str] | None,
    file_paths: list[str] | None = None,
) -> set[str] | None:
    metadata = _load_metadata(workspace)
    candidates: set[str] | None = None

    if topics:
        topic_ids: set[str] = set()
        for t in topics:
            topic_ids.update(metadata.get("topics", {}).get(t, []))
        candidates = topic_ids

    if tags:
        tag_ids: set[str] = set()
        for t in tags:
            tag_ids.update(metadata.get("tags", {}).get(t, []))
        if candidates is None:
            candidates = tag_ids
        else:
            candidates &= tag_ids

    if file_paths:
        file_ids: set[str] = set()
        for path in file_paths:
            file_ids.update(metadata.get("files", {}).get(path, []))
        if candidates is None:
            candidates = file_ids
        else:
            candidates &= file_ids

    return candidates


def hybrid_search(
    workspace: str,
    query_dense: list[float],
    top_k: int = 10,
    topics: list | None = None,
    tags: list | None = None,
    query_text: str = "",
    file_paths: list[str] | None = None,
) -> list[dict]:
    collection = _get_collection(workspace)

    candidates = _filter_candidates(workspace, topics, tags, file_paths)

    bm25_active = False
    if query_text:
        bm25_active = ensure_bm25_index(workspace)
        if not bm25_active:
            logger.warning("[rag/index] BM25 unavailable after ensure — dense-only fallback")

    dense_future = _HYBRID_POOL.submit(_dense_search, collection, query_dense, candidates, top_k)
    sparse_future = None
    if query_text and bm25_active:
        sparse_future = _HYBRID_POOL.submit(_sparse_search, workspace, query_text, candidates, top_k)

    dense_results = dense_future.result()
    sparse_scores: dict[str, float] = sparse_future.result() if sparse_future else {}
    sparse_scores = _normalize_sparse_scores(sparse_scores)

    dense_map = {r["id"]: r for r in dense_results}

    dense_weight, sparse_weight = hybrid_weights()

    # Merge dense + sparse (BM25 normalized to 0..1 when active)
    results_map = {}
    for cid, r in dense_map.items():
        sparse = sparse_scores.get(cid, 0.0)
        r["sparse_score"] = sparse
        r["bm25_used"] = bm25_active
        r["score"] = dense_weight * r["dense_score"] + sparse_weight * sparse
        results_map[cid] = r

    # Add sparse-only hits
    if sparse_scores:
        sparse_ids = [cid for cid in sparse_scores if cid not in results_map]
        if sparse_ids:
            try:
                fetched = collection.fetch(
                    sparse_ids,
                    output_fields=["content", "file_path", "topic", "tags_json", "section_title"],
                    include_vector=True,
                )
                for cid, doc in fetched.items():
                    if cid not in sparse_scores:
                        continue
                    r = _doc_to_result(doc)
                    r["sparse_score"] = sparse_scores[cid]
                    r["bm25_used"] = True
                    r["score"] = sparse_weight * sparse_scores[cid]
                    results_map[cid] = r
            except Exception as e:
                logger.warning(f"[rag/index] sparse-only fetch failed: {e}\n")

    sorted_results = sorted(results_map.values(), key=lambda x: x["score"], reverse=True)
    return filter_usable_chunks(sorted_results)[:top_k]


def _get_chunks_by_file(workspace: str, file_path: str) -> list[dict]:
    try:
        collection = _get_collection(workspace)
        filter_expr = f"file_path = {_escape_filter_value(file_path)}"
        docs = collection.query(filter=filter_expr, topk=10000, output_fields=[])
        return [{"id": doc.id} for doc in docs]
    except Exception as e:
        log_exception(f"[rag/index] failed to get chunks for file {file_path}", e, level="warning", logger=logger)
        return []


def fetch_chunks_by_file(workspace: str, file_path: str, limit: int = 2) -> list[dict]:
    try:
        collection = _get_collection(workspace)
        filter_expr = f"file_path = {_escape_filter_value(file_path)}"
        docs = collection.query(
            filter=filter_expr,
            topk=limit,
            output_fields=["content", "file_path", "topic", "tags_json", "section_title"],
        )
        return [_doc_to_result(doc) for doc in docs]
    except Exception as e:
        logger.warning(f"[rag/index] fetch_chunks_by_file error: {e}\n")
        return []
