"""Lightweight local RAG index using zvec + BM25s.

Schema:
- zvec collection: dense vectors + chunk metadata
- bm25s corpus + index files alongside the collection
- metadata.json: topic/tag inverted indices for fast filtering
"""

from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import bm25s
import zvec

from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from utils.error_handler import log_exception
from utils.logger import logger

_COLLECTION_NAME = "noteai_chunks"
_DENSE_DIM = 512
_DENSE_METRIC = zvec.MetricType.COSINE
_BM25_K1 = 1.5
_BM25_B = 0.75

_INDEX_BATCH_SIZE = 128
_FETCH_BATCH_SIZE = 256
_HYBRID_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag_hybrid")
_DENSE_EF_CAP = 128
_DENSE_EF_MULTIPLIER = 8

_lock = threading.Lock()

# Cache opened collections per workspace to avoid repeated zvec.open() cost
# (zvec.open reloads the mmindex every time, which is expensive for large indices).
_COLLECTION_CACHE: dict[str, zvec.Collection] = {}
_COLLECTION_CACHE_LOCK = threading.Lock()

# In-memory BM25 retriever cache (bm25s.load is costly on every query).
_BM25_CACHE: dict[str, tuple[Any, list[dict]]] = {}
_BM25_CACHE_LOCK = threading.Lock()
_ENSURE_BM25_LOCK = threading.Lock()
_ENSURE_BM25_IN_PROGRESS: set[str] = set()


def _rag_index_dir(workspace: str) -> Path:
    return Path(workspace) / WORKSPACE_APP_FOLDER / RAG_INDEX_FOLDER


def _collection_path(workspace: str) -> Path:
    p = _rag_index_dir(workspace) / "zvec_collection"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _bm25s_dir(workspace: str) -> Path:
    p = _rag_index_dir(workspace) / "bm25s"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _metadata_path(workspace: str) -> Path:
    return _rag_index_dir(workspace) / "metadata.json"


def _manifest_path(workspace: str) -> Path:
    return _rag_index_dir(workspace) / "manifest.json"


_INDEX_VERSION = 2


def _read_manifest(workspace: str) -> dict:
    """Read the index manifest, returning a default if missing or invalid."""
    path = _manifest_path(workspace)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_manifest(workspace: str, data: dict) -> None:
    """Atomically write the index manifest."""
    import tempfile as _tempfile

    path = _manifest_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        log_exception("[rag/index] failed to write manifest", e, level="warning", logger=logger)


def _manifest_version_ok(workspace: str) -> bool:
    """Check whether the on-disk index version matches the current schema version."""
    manifest = _read_manifest(workspace)
    return manifest.get("version") == _INDEX_VERSION


def _bump_manifest_version(workspace: str) -> None:
    manifest = _read_manifest(workspace)
    manifest["version"] = _INDEX_VERSION
    manifest["schema_version"] = _INDEX_VERSION
    import time as _time

    manifest["last_rebuilt"] = _time.time()
    _write_manifest(workspace, manifest)


def _build_schema() -> zvec.CollectionSchema:
    return zvec.CollectionSchema(
        name=_COLLECTION_NAME,
        fields=[
            zvec.FieldSchema("content", zvec.DataType.STRING),
            zvec.FieldSchema("file_path", zvec.DataType.STRING, index_param=zvec.InvertIndexParam()),
            zvec.FieldSchema("topic", zvec.DataType.STRING, index_param=zvec.InvertIndexParam()),
            zvec.FieldSchema("tags_json", zvec.DataType.STRING),
            zvec.FieldSchema("section_title", zvec.DataType.STRING),
        ],
        vectors=[
            zvec.VectorSchema(
                "dense",
                zvec.DataType.VECTOR_FP32,
                dimension=_DENSE_DIM,
                index_param=zvec.HnswIndexParam(metric_type=_DENSE_METRIC),
            ),
        ],
    )


def _get_collection(workspace: str) -> zvec.Collection:
    with _COLLECTION_CACHE_LOCK:
        cached = _COLLECTION_CACHE.get(workspace)
        if cached is not None and _manifest_version_ok(workspace):
            return cached
        # Version mismatch or no cache — drop stale entry before reopening.
        _COLLECTION_CACHE.pop(workspace, None)

    path = str(_collection_path(workspace))
    try:
        if not _manifest_version_ok(workspace) and Path(path).exists():
            logger.info("[RAG] index version mismatch, rebuilding collection")
            shutil.rmtree(path, ignore_errors=True)
            _bm25s = _bm25s_dir(workspace)
            if _bm25s.exists():
                shutil.rmtree(_bm25s, ignore_errors=True)
        collection = zvec.open(path)
    except Exception as e:
        log_exception("[rag/index] failed to open existing collection, creating new", e, level="info", logger=logger)
        collection = zvec.create_and_open(path, _build_schema())

    with _COLLECTION_CACHE_LOCK:
        _COLLECTION_CACHE[workspace] = collection
    return collection


def clear_bm25_cache(workspace: str | None = None) -> None:
    """Drop cached BM25 retriever(s)."""
    with _BM25_CACHE_LOCK:
        if workspace is None:
            _BM25_CACHE.clear()
        else:
            _BM25_CACHE.pop(workspace, None)


def clear_collection_cache(workspace: str | None = None) -> None:
    """Drop cached collection(s). Useful before/after full rebuilds or tests."""
    with _COLLECTION_CACHE_LOCK:
        if workspace is None:
            _COLLECTION_CACHE.clear()
        else:
            _COLLECTION_CACHE.pop(workspace, None)
    clear_bm25_cache(workspace)


def _escape_filter_value(value: str) -> str:
    """Escape a string for use in a zvec filter expression."""
    text = str(value)
    if "\x00" in text:
        raise ValueError("filter value contains null byte")
    if any(ord(ch) < 32 for ch in text):
        raise ValueError("filter value contains control characters")
    return "'" + text.replace("'", "''") + "'"


def is_usable_chunk(result: dict) -> bool:
    content = (result.get("content") or "").strip()
    return bool(content)


def filter_usable_chunks(results: list[dict]) -> list[dict]:
    return [r for r in results if is_usable_chunk(r)]


def index_exists(workspace: str) -> bool:
    return _collection_path(workspace).exists() and _metadata_path(workspace).exists()


def count_indexed_chunks(workspace: str) -> int:
    """Return approximate chunk count from the metadata inverted index.

    Cross-checks the actual collection count when available and falls back to
    metadata when the collection is empty or inaccessible.
    """
    metadata = _load_metadata(workspace)
    files = metadata.get("files") or {}
    metadata_total = 0
    for ids in files.values():
        metadata_total += len(ids)

    try:
        collection_count = _collection_count(workspace)
    except Exception as e:
        log_exception("[rag/index] failed to get collection count", e, level="debug", logger=logger)
        collection_count = -1

    if collection_count >= 0 and metadata_total != collection_count:
        logger.warning(
            f"Chunk count mismatch: metadata={metadata_total}, collection={collection_count}; "
            f"using collection count"
        )
        return collection_count
    return metadata_total


def _collection_count(workspace: str) -> int:
    """Query the zvec collection for total entity count, or -1 if unavailable."""
    try:
        import zvec

        collection = zvec.Collection(str(_collection_path(workspace)))
        return int(collection.num_entities)
    except Exception as e:
        log_exception("[rag/index] failed to query collection count", e, level="debug", logger=logger)
        return -1


def _empty_metadata() -> dict[str, Any]:
    return {"topics": {}, "tags": {}, "files": {}, "version": 2}


def _load_metadata(workspace: str) -> dict[str, Any]:
    path = _metadata_path(workspace)
    if not path.exists():
        return _empty_metadata()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("topics", {})
                data.setdefault("tags", {})
                data.setdefault("files", {})
                return data
    except Exception as e:
        log_exception("[rag/index] failed to load metadata", e, level="warning", logger=logger)
    return _empty_metadata()


def _save_metadata(workspace: str, metadata: dict[str, Any]) -> None:
    path = _metadata_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)
    tmp.replace(path)


def _update_metadata_index(metadata: dict[str, Any], chunk: dict, mode: str = "add") -> None:
    chunk_id = chunk["id"]
    topic = chunk.get("topic") or ""
    tags = chunk.get("tags") or []
    file_path = chunk.get("file_path") or ""

    def _mutate(key: str, value: str) -> None:
        if not value:
            return
        bucket = metadata.setdefault(key, {})
        ids = set(bucket.get(value, []))
        if mode == "add":
            ids.add(chunk_id)
        else:
            ids.discard(chunk_id)
        if ids:
            bucket[value] = sorted(ids)
        else:
            bucket.pop(value, None)

    _mutate("topics", topic)
    _mutate("files", file_path)
    for tag in tags:
        _mutate("tags", tag)


def _chunk_to_doc(chunk: dict, embedding: dict) -> zvec.Doc:
    cid = chunk.get("id", "")
    content = (chunk.get("content") or "")[:8192]
    file_path = (chunk.get("file_path") or "")[:512]
    topic = (chunk.get("topic") or "")[:256]
    tags = chunk.get("tags") or []
    section_title = (chunk.get("section_title") or "")[:256]
    vec = embedding.get("dense_vec") or [0.0] * _DENSE_DIM

    return zvec.Doc(
        id=cid,
        vectors={"dense": vec},
        fields={
            "content": content,
            "file_path": file_path,
            "topic": topic,
            "tags_json": json.dumps(tags, ensure_ascii=False),
            "section_title": section_title,
        },
    )


def _tags_from_fields(fields: dict) -> list[str]:
    try:
        return json.loads(fields.get("tags_json") or "[]")
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        log_exception("[rag/index] failed to parse tags_json", e, level="debug", logger=logger)
        return []


def _doc_to_result(doc: zvec.Doc, score: float | None = None) -> dict:
    fields = doc.fields or {}
    return {
        "id": doc.id,
        "content": fields.get("content", ""),
        "file_path": fields.get("file_path", ""),
        "topic": fields.get("topic", ""),
        "tags": _tags_from_fields(fields),
        "section_title": fields.get("section_title", ""),
        "dense_vec": None,
        "dense_score": score if score is not None else 0.0,
        "sparse_score": 0.0,
        "score": score if score is not None else 0.0,
    }


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


def build_index(workspace: str, chunks: list[dict], embeddings: list[dict], progress_callback=None) -> dict[str, Any]:
    index_dir = _rag_index_dir(workspace)
    index_dir.mkdir(parents=True, exist_ok=True)

    collection_path = _collection_path(workspace)
    # Drop any cached collection before wiping the directory, then cache the new one.
    clear_collection_cache(workspace)
    if collection_path.exists():
        shutil.rmtree(collection_path, ignore_errors=True)
    for old in index_dir.glob("*.tmp"):
        old.unlink()

    collection = zvec.create_and_open(str(collection_path), _build_schema())
    with _COLLECTION_CACHE_LOCK:
        _COLLECTION_CACHE[workspace] = collection

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

    # Build BM25s index
    if progress_callback:
        progress_callback(total, total, "构建 BM25 索引...")

    _build_and_save_bm25(chunks, _bm25s_dir(workspace), workspace)

    # Build metadata indices
    metadata = _empty_metadata()
    for chunk in chunks:
        _update_metadata_index(metadata, chunk, mode="add")
    _save_metadata(workspace, metadata)

    _bump_manifest_version(workspace)

    return {"success": True, "chunk_count": total}


def add_chunks(workspace: str, chunks: list[dict], embeddings: list[dict]) -> None:
    if not chunks:
        return

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

    collection.upsert(docs)
    collection.flush()
    _save_metadata(workspace, metadata)

    # Rebuild BM25s with merged corpus
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
    if collection is None:
        collection = _get_collection(workspace)
    metadata = _load_metadata(workspace)

    removed: list[dict] = []
    try:
        filter_expr = f"file_path = {_escape_filter_value(file_path)}"
        docs = collection.query(filter=filter_expr, topk=10000, output_fields=["content", "file_path", "topic", "tags_json", "section_title"])
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

    if removed:
        ids = [c["id"] for c in removed]
        collection.delete(ids)
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
    except Exception as e:
        logger.warning(f"[rag/index] BM25s rebuild after delete failed: {e}\n")

    return removed


def _chunk_ids_from_metadata(workspace: str) -> list[str]:
    """Collect all chunk ids tracked in metadata inverted indices."""
    metadata = _load_metadata(workspace)
    ids: set[str] = set()
    for bucket in (metadata.get("topics", {}), metadata.get("tags", {}), metadata.get("files", {})):
        for id_list in bucket.values():
            ids.update(id_list)
    return sorted(ids)


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
                    if int(_get_collection(workspace).num_entities) == 0:
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


def _filter_candidates(workspace: str, topics: list[str] | None, tags: list[str] | None) -> set[str] | None:
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

    return candidates


def hybrid_search(
    workspace: str,
    query_dense: list[float],
    query_sparse: dict | None = None,
    top_k: int = 10,
    topics: list | None = None,
    tags: list | None = None,
    query_text: str = "",
) -> list[dict]:
    collection = _get_collection(workspace)

    candidates = _filter_candidates(workspace, topics, tags)

    if not query_text and query_sparse:
        query_text = " ".join(str(k) for k, v in query_sparse.items() if v > 0)

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

    # Merge dense + sparse (BM25 normalized to 0..1 when active)
    results_map = {}
    for cid, r in dense_map.items():
        sparse = sparse_scores.get(cid, 0.0)
        r["sparse_score"] = sparse
        r["bm25_used"] = bm25_active
        r["score"] = 0.7 * r["dense_score"] + 0.3 * sparse
        results_map[cid] = r

    # Add sparse-only hits
    if sparse_scores:
        sparse_ids = [cid for cid in sparse_scores if cid not in results_map]
        if sparse_ids:
            try:
                fetched = collection.fetch(
                    sparse_ids,
                    output_fields=["content", "file_path", "topic", "tags_json", "section_title"],
                    include_vector=False,
                )
                for cid, doc in fetched.items():
                    if cid not in sparse_scores:
                        continue
                    r = _doc_to_result(doc)
                    r["sparse_score"] = sparse_scores[cid]
                    r["bm25_used"] = True
                    r["score"] = 0.3 * sparse_scores[cid]
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


def manifest_path(workspace: str) -> Path:
    return _rag_index_dir(workspace) / "file_manifest.json"


def load_manifest(workspace: str) -> dict[str, Any]:
    path = manifest_path(workspace)
    if not path.exists():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "files" in data:
            data.setdefault("version", 1)
            return data
    except Exception as e:
        log_exception("[rag/index] failed to load file manifest", e, level="warning", logger=logger)
    return {"version": 1, "files": {}}


def save_manifest(workspace: str, manifest: dict[str, Any]) -> None:
    path = manifest_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    tmp.replace(path)


def rebuild_search_indices(workspace: str, all_chunk_ids: list[str], progress_callback=None) -> int:
    """Rebuild BM25s and metadata from all chunks currently in the zvec collection.

    Returns the number of chunks in the rebuilt indices.
    """
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
