"""BM25s index build, cache, sparse search, and hybrid-index rebuild."""

from __future__ import annotations

import threading
from pathlib import Path

import bm25s
import zvec

from sidecar.rag.index_core import (
    _BM25_CACHE,
    _BM25_CACHE_LOCK,
    _FETCH_BATCH_SIZE,
    _bm25s_dir,
    _chunk_ids_from_metadata,
    _empty_metadata,
    _get_collection,
    _save_metadata,
    _tags_from_fields,
    _update_metadata_index,
    clear_bm25_cache,
)
from utils.error_handler import log_exception
from utils.logger import logger

_BM25_K1 = 1.5
_BM25_B = 0.75
_ENSURE_BM25_LOCK = threading.Lock()
_ENSURE_BM25_IN_PROGRESS: set[str] = set()


def _bm25_corpus_from_retriever(retriever) -> list[dict]:
    """Extract the document corpus from a loaded bm25s retriever."""
    corpus = retriever.corpus
    if isinstance(corpus, dict):
        return corpus.get("documents", [])
    return corpus or []


def _build_and_save_bm25(corpus: list[dict], bm25_dir: Path, workspace: str) -> None:
    """Tokenize, index and save a BM25s retriever with the given corpus."""
    if not corpus:
        if bm25_dir.exists():
            for f in bm25_dir.iterdir():
                f.unlink()
        clear_bm25_cache(workspace)
        return
    tokenized = bm25s.tokenize([c.get("content", "") for c in corpus], stopwords="zh")
    retriever = bm25s.BM25(corpus=corpus, k1=_BM25_K1, b=_BM25_B)
    retriever.index(tokenized)
    retriever.save(bm25_dir, corpus=corpus)
    clear_bm25_cache(workspace)


def bm25_index_ready(workspace: str) -> bool:
    """Return True when a non-empty BM25 index is loadable for *workspace*."""
    retriever, corpus = _load_bm25_retriever(workspace)
    return retriever is not None and bool(corpus)


def ensure_bm25_index(workspace: str) -> bool:
    """Ensure BM25 index exists; rebuild from zvec when missing but vectors are present."""
    if bm25_index_ready(workspace):
        return True

    with _ENSURE_BM25_LOCK:
        if bm25_index_ready(workspace):
            return True
        if workspace in _ENSURE_BM25_IN_PROGRESS:
            return bm25_index_ready(workspace)
        _ENSURE_BM25_IN_PROGRESS.add(workspace)
        try:
            chunk_ids = _chunk_ids_from_metadata(workspace)
            if not chunk_ids:
                try:
                    if int(_get_collection(workspace).stats.doc_count) == 0:
                        return False
                except Exception:
                    return False
                logger.warning("[rag/index] BM25 missing and metadata has no chunk ids")
                return False

            logger.info(f"[rag/index] BM25 index missing — rebuilding from {len(chunk_ids)} chunks")
            rebuild_search_indices(workspace, chunk_ids)
            return bm25_index_ready(workspace)
        except Exception as e:
            log_exception("[rag/index] ensure_bm25_index failed", e, level="warning", logger=logger)
            return False
        finally:
            _ENSURE_BM25_IN_PROGRESS.discard(workspace)


def _load_bm25_retriever(workspace: str):
    with _BM25_CACHE_LOCK:
        cached = _BM25_CACHE.get(workspace)
        if cached is not None:
            return cached

    bm25_dir = _bm25s_dir(workspace)
    if not bm25_dir.exists() or not any(bm25_dir.iterdir()):
        return None, []
    try:
        retriever = bm25s.BM25.load(bm25_dir, load_corpus=True)
        corpus = _bm25_corpus_from_retriever(retriever)
        if retriever is not None and corpus:
            with _BM25_CACHE_LOCK:
                _BM25_CACHE[workspace] = (retriever, corpus)
            return retriever, corpus
        return None, []
    except Exception as e:
        log_exception("[rag/index] failed to load BM25 retriever", e, level="warning", logger=logger)
        return None, []


def _normalize_sparse_scores(scores: dict[str, float]) -> dict[str, float]:
    """Scale BM25 scores to 0..1 for stable hybrid fusion."""
    if not scores:
        return scores
    peak = max(scores.values())
    if peak <= 0:
        return scores
    return {cid: val / peak for cid, val in scores.items()}


def _sparse_search(
    workspace: str,
    query_text: str,
    candidate_ids: set[str] | None,
    top_k: int,
) -> dict[str, float]:
    retriever, corpus = _load_bm25_retriever(workspace)
    if retriever is None or not corpus:
        return {}

    query_tokens = bm25s.tokenize([query_text], stopwords="zh")
    results, scores = retriever.retrieve(query_tokens, k=min(top_k * 4, len(corpus)))

    out: dict[str, float] = {}
    if results.size == 0:
        return out

    for hit_arr, score_arr in zip(results, scores, strict=False):
        for hit, score in zip(hit_arr, score_arr, strict=False):
            score = float(score)
            if score <= 0:
                continue
            cid = hit.get("id", "") if isinstance(hit, dict) else ""
            if not cid:
                continue
            if candidate_ids is not None and cid not in candidate_ids:
                continue
            out[cid] = max(out.get(cid, 0.0), score)
    return out


def rebuild_search_indices(
    workspace: str,
    all_chunk_ids: list[str],
    progress_callback=None,
    collection: zvec.Collection | None = None,
) -> int:
    """Rebuild BM25s and metadata from all chunks currently in the zvec collection.

    Returns the number of chunks in the rebuilt indices.
    """
    if collection is None:
        collection = _get_collection(workspace)
    corpus: list[dict] = []

    batch_size = _FETCH_BATCH_SIZE
    total = len(all_chunk_ids)
    for i in range(0, total, batch_size):
        batch = all_chunk_ids[i : i + batch_size]
        fetched = collection.fetch(
            batch,
            output_fields=["content", "file_path", "topic", "tags_json", "section_title"],
            include_vector=False,
        )
        for cid, doc in fetched.items():
            fields = doc.fields or {}
            corpus.append(
                {
                    "id": cid,
                    "content": fields.get("content", ""),
                    "file_path": fields.get("file_path", ""),
                    "topic": fields.get("topic", ""),
                    "tags": _tags_from_fields(fields),
                    "section_title": fields.get("section_title", ""),
                }
            )
        if progress_callback:
            progress_callback(min(i + batch_size, total), total, "重建检索索引")

    if not corpus:
        return 0

    # Rebuild metadata
    metadata = _empty_metadata()
    for chunk in corpus:
        _update_metadata_index(metadata, chunk, mode="add")
    _save_metadata(workspace, metadata)

    # Rebuild BM25s
    if progress_callback:
        progress_callback(total, total, "重建 BM25 索引")
    _build_and_save_bm25(corpus, _bm25s_dir(workspace), workspace)

    return len(corpus)
