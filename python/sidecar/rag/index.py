import json
import math
import os
import shutil
import threading
from pathlib import Path

from pymilvus import DataType, MilvusClient

from config import config
from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from utils.logger import logger

_COLLECTION_NAME = "noteai_chunks"
_DENSE_DIM = 512
_BM25_K1 = 1.5
_BM25_B = 0.75
_load_lock = threading.Lock()
_zvec_lock = threading.Lock()
_zvec_collections: dict[str, object] = {}


def is_usable_chunk(result: dict) -> bool:
    """Drop hits with no body text — sparse-only Milvus rows can be metadata-only."""
    content = (result.get("content") or "").strip()
    return bool(content)


def filter_usable_chunks(results: list[dict]) -> list[dict]:
    return [r for r in results if is_usable_chunk(r)]


def _db_path(workspace: str) -> str:
    p = _rag_index_dir(workspace) / "milvus_lite.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _rag_index_dir(workspace: str) -> Path:
    return Path(workspace) / WORKSPACE_APP_FOLDER / RAG_INDEX_FOLDER


def _get_client(workspace: str) -> MilvusClient:
    return MilvusClient(uri=_db_path(workspace))


def _vector_store_backend() -> str:
    value = os.environ.get("NOTEAI_VECTOR_STORE") or getattr(config, "rag_vector_store", "zvec") or "zvec"
    value = value.strip().lower().replace("-", "_")
    if value in {"milvus", "milvus_lite"}:
        return "milvus_lite"
    return "zvec"


def _use_zvec() -> bool:
    return _vector_store_backend() == "zvec"


def _zvec_path(workspace: str) -> Path:
    return _rag_index_dir(workspace) / "zvec_collection"


def _zvec_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _zvec_schema():
    import zvec

    return zvec.CollectionSchema(
        name=_COLLECTION_NAME,
        fields=[
            zvec.FieldSchema("content", zvec.DataType.STRING, nullable=True),
            zvec.FieldSchema("file_path", zvec.DataType.STRING, nullable=True),
            zvec.FieldSchema("topic", zvec.DataType.STRING, nullable=True),
            zvec.FieldSchema("tags", zvec.DataType.STRING, nullable=True),
            zvec.FieldSchema("section_title", zvec.DataType.STRING, nullable=True),
        ],
        vectors=[
            zvec.VectorSchema(
                "dense_vec",
                zvec.DataType.VECTOR_FP32,
                dimension=_DENSE_DIM,
                index_param=zvec.FlatIndexParam(),
            )
        ],
    )


def _open_zvec_collection(workspace: str, *, create: bool = False):
    import zvec

    path = _zvec_path(workspace)
    key = str(path)
    with _zvec_lock:
        if key in _zvec_collections:
            return _zvec_collections[key]
        if path.exists():
            collection = zvec.open(str(path))
            _zvec_collections[key] = collection
            return collection
        if not create:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        collection = zvec.create_and_open(str(path), _zvec_schema())
        _zvec_collections[key] = collection
        return collection


def _close_cached_zvec_collection(workspace: str) -> None:
    path = _zvec_path(workspace)
    key = str(path)
    with _zvec_lock:
        collection = _zvec_collections.pop(key, None)
    if collection is not None and hasattr(collection, "flush"):
        try:
            collection.flush()
        except Exception:
            pass


def _zvec_doc_to_result(doc) -> dict:
    fields = doc.fields or {}
    tags_val = fields.get("tags", "[]")
    try:
        tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
    except Exception:
        tags_list = []
    return {
        "id": doc.id,
        "content": fields.get("content", ""),
        "file_path": fields.get("file_path", ""),
        "topic": fields.get("topic", ""),
        "tags": tags_list,
        "section_title": fields.get("section_title", ""),
        "dense_score": float(doc.score or 0.0),
        "sparse_score": 0.0,
        "score": float(doc.score or 0.0),
    }


def _zvec_passes_filters(result: dict, topics: list | None, tags: list | None) -> bool:
    if topics and result.get("topic") not in topics:
        return False
    if tags:
        result_tags = result.get("tags") or []
        if not any(tag in result_tags for tag in tags):
            return False
    return True


def _collection_exists(client: MilvusClient) -> bool:
    return client.has_collection(_COLLECTION_NAME)


def _ensure_collection_loaded(_workspace: str, client: MilvusClient) -> bool:
    """Milvus Lite keeps collections 'released' until load(); required before search/query."""
    if not _collection_exists(client):
        return False
    with _load_lock:
        try:
            client.load_collection(collection_name=_COLLECTION_NAME)
            return True
        except Exception as e:
            err = str(e).lower()
            if "already" in err or "loaded" in err:
                return True
            logger.warning(f"[rag/index] load_collection failed: {e}\n")
            return False


def _create_collection(client: MilvusClient):
    from pymilvus import CollectionSchema, FieldSchema

    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=256),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8192),
        FieldSchema(name="file_path", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="topic", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="tags", dtype=DataType.VARCHAR, max_length=1024),
        FieldSchema(name="section_title", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="dense_vec", dtype=DataType.FLOAT_VECTOR, dim=_DENSE_DIM),
    ]
    schema = CollectionSchema(fields, enable_dynamic_field=True)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense_vec",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        params={"nlist": 128},
    )

    client.create_collection(
        collection_name=_COLLECTION_NAME,
        schema=schema,
        index_params=index_params,
    )


def index_exists(workspace: str) -> bool:
    if _use_zvec():
        try:
            return _open_zvec_collection(workspace) is not None
        except Exception:
            return False
    try:
        client = _get_client(workspace)
        return _collection_exists(client)
    except Exception:
        return False


def build_index(workspace: str, chunks: list[dict], embeddings: list[dict], progress_callback=None):
    if _use_zvec():
        return _build_index_zvec(workspace, chunks, embeddings, progress_callback=progress_callback)

    client = _get_client(workspace)

    if _collection_exists(client):
        client.drop_collection(_COLLECTION_NAME)

    _create_collection(client)

    batch_size = 100
    total = len(chunks)

    for i in range(0, total, batch_size):
        batch_chunks = chunks[i:i + batch_size]
        batch_embeds = embeddings[i:i + batch_size]

        data = []
        for chunk, emb in zip(batch_chunks, batch_embeds, strict=False):
            tags_str = json.dumps(chunk.get("tags", []), ensure_ascii=False)
            row = {
                "id": chunk.get("id", f"chunk_{i}"),
                "content": (chunk.get("content") or "")[:8192],
                "file_path": (chunk.get("file_path") or "")[:512],
                "topic": (chunk.get("topic") or "")[:256],
                "tags": tags_str[:1024],
                "section_title": (chunk.get("section_title") or "")[:256],
                "dense_vec": emb.get("dense_vec", [0.0] * _DENSE_DIM),
            }
            data.append(row)

        client.insert(collection_name=_COLLECTION_NAME, data=data)

        if progress_callback:
            progress_callback(min(i + batch_size, total), total, "写入索引")

    _save_sparse_index(workspace, chunks, embeddings)
    _ensure_collection_loaded(workspace, client)

    return {"success": True, "chunk_count": total}


def _build_index_zvec(workspace: str, chunks: list[dict], embeddings: list[dict], progress_callback=None):
    import zvec

    path = _zvec_path(workspace)
    if path.exists():
        _close_cached_zvec_collection(workspace)
        shutil.rmtree(path, ignore_errors=True)

    collection = _open_zvec_collection(workspace, create=True)
    batch_size = 100
    total = len(chunks)

    for i in range(0, total, batch_size):
        batch_chunks = chunks[i:i + batch_size]
        batch_embeds = embeddings[i:i + batch_size]
        docs = []
        for chunk, emb in zip(batch_chunks, batch_embeds, strict=False):
            tags_str = json.dumps(chunk.get("tags", []), ensure_ascii=False)
            docs.append(zvec.Doc(
                id=chunk.get("id", f"chunk_{i}"),
                vectors={"dense_vec": emb.get("dense_vec", [0.0] * _DENSE_DIM)},
                fields={
                    "content": (chunk.get("content") or "")[:8192],
                    "file_path": (chunk.get("file_path") or "")[:512],
                    "topic": (chunk.get("topic") or "")[:256],
                    "tags": tags_str[:1024],
                    "section_title": (chunk.get("section_title") or "")[:256],
                },
            ))
        if docs:
            collection.insert(docs)
        if progress_callback:
            progress_callback(min(i + batch_size, total), total, "写入 zvec 索引")

    collection.flush()
    _save_sparse_index(workspace, chunks, embeddings)
    return {"success": True, "chunk_count": total, "backend": "zvec"}


def _sparse_index_path(workspace: str) -> Path:
    return _rag_index_dir(workspace) / "sparse_index.json"


def _normalize_lexical_counts(raw: dict | None) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    counts = {}
    for key, value in raw.items():
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if v > 0:
            counts[str(key)] = v
    return counts


def _build_bm25_index(chunks: list[dict], embeddings: list[dict]) -> dict:
    docs = {}
    df = {}
    for chunk, emb in zip(chunks, embeddings, strict=False):
        chunk_id = chunk.get("id", "")
        if not chunk_id:
            continue
        terms = _normalize_lexical_counts(emb.get("lexical_weights", {}))
        doc_len = float(sum(terms.values()))
        docs[chunk_id] = {"terms": terms, "doc_len": doc_len}
        for term in terms:
            df[term] = df.get(term, 0) + 1

    total_len = sum(doc.get("doc_len", 0.0) for doc in docs.values())
    doc_count = len(docs)
    avgdl = total_len / doc_count if doc_count else 0.0
    return {
        "version": 2,
        "kind": "bm25",
        "doc_count": doc_count,
        "avgdl": avgdl,
        "df": df,
        "docs": docs,
    }


def _is_bm25_index(data: dict) -> bool:
    return data.get("version") == 2 and data.get("kind") == "bm25" and isinstance(data.get("docs"), dict)


def _recompute_bm25_stats(index: dict) -> dict:
    docs = index.get("docs", {}) if isinstance(index, dict) else {}
    df = {}
    total_len = 0.0
    for doc in docs.values():
        terms = _normalize_lexical_counts(doc.get("terms", {}))
        doc["terms"] = terms
        doc_len = float(doc.get("doc_len") or sum(terms.values()))
        doc["doc_len"] = doc_len
        total_len += doc_len
        for term in terms:
            df[term] = df.get(term, 0) + 1
    doc_count = len(docs)
    index["version"] = 2
    index["kind"] = "bm25"
    index["doc_count"] = doc_count
    index["avgdl"] = total_len / doc_count if doc_count else 0.0
    index["df"] = df
    index["docs"] = docs
    return index


def _save_sparse_index(workspace: str, chunks: list[dict], embeddings: list[dict]):
    path = _sparse_index_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_build_bm25_index(chunks, embeddings), ensure_ascii=False), encoding="utf-8")


def _load_sparse_index(workspace: str) -> dict:
    path = _sparse_index_path(workspace)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _purge_stale_sparse_ids(workspace: str, stale_ids: list[str]):
    path = _sparse_index_path(workspace)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        if _is_bm25_index(data):
            docs = data.get("docs", {})
            for cid in stale_ids:
                if cid in docs:
                    del docs[cid]
                    changed = True
            if changed:
                _recompute_bm25_stats(data)
        else:
            for cid in stale_ids:
                if cid in data:
                    del data[cid]
                    changed = True
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            logger.debug("Purged %d stale sparse index entries", len(stale_ids))
    except Exception:
        pass


def _legacy_sparse_scores(query_sparse: dict, sparse_index: dict) -> dict[str, float]:
    sparse_scores = {}
    query_norm = sum(v * v for v in query_sparse.values()) ** 0.5
    if query_norm <= 0:
        return sparse_scores
    for chunk_id, doc_sparse in sparse_index.items():
        if not isinstance(doc_sparse, dict):
            continue
        dot = 0.0
        for k, v in query_sparse.items():
            str_k = str(k)
            if str_k in doc_sparse:
                dot += v * doc_sparse[str_k]
        if dot > 0:
            sparse_scores[chunk_id] = dot / query_norm
    return sparse_scores


def _bm25_scores(query_sparse: dict, sparse_index: dict) -> dict[str, float]:
    if not query_sparse or not _is_bm25_index(sparse_index):
        return {}
    docs = sparse_index.get("docs", {})
    df = sparse_index.get("df", {})
    doc_count = int(sparse_index.get("doc_count") or len(docs))
    avgdl = float(sparse_index.get("avgdl") or 0.0)
    if not docs or doc_count <= 0 or avgdl <= 0:
        return {}

    query_terms = _normalize_lexical_counts(query_sparse)
    raw_scores = {}
    for term, query_tf in query_terms.items():
        term_df = int(df.get(term, 0))
        if term_df <= 0:
            continue
        idf = math.log(1.0 + (doc_count - term_df + 0.5) / (term_df + 0.5))
        for chunk_id, doc in docs.items():
            terms = doc.get("terms", {})
            tf = float(terms.get(term, 0.0))
            if tf <= 0:
                continue
            doc_len = float(doc.get("doc_len") or sum(float(v) for v in terms.values()))
            denom = tf + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * doc_len / avgdl)
            if denom <= 0:
                continue
            score = idf * (tf * (_BM25_K1 + 1.0) / denom) * min(query_tf, 3.0)
            raw_scores[chunk_id] = raw_scores.get(chunk_id, 0.0) + score

    if not raw_scores:
        return {}
    max_score = max(raw_scores.values())
    if max_score <= 0:
        return {}
    return {chunk_id: score / max_score for chunk_id, score in raw_scores.items()}


def _lexical_scores(query_sparse: dict, sparse_index: dict) -> dict[str, float]:
    if _is_bm25_index(sparse_index):
        return _bm25_scores(query_sparse, sparse_index)
    return _legacy_sparse_scores(query_sparse, sparse_index)


def hybrid_search(
    workspace: str,
    query_dense: list[float],
    query_sparse: dict,
    top_k: int = 10,
    topics: list = None,
    tags: list = None,
) -> list[dict]:
    if _use_zvec():
        return _hybrid_search_zvec(workspace, query_dense, query_sparse, top_k=top_k, topics=topics, tags=tags)

    client = _get_client(workspace)

    if not _ensure_collection_loaded(workspace, client):
        return []

    filter_expr = None
    conditions = []
    if topics:
        safe_topics = [t.replace('"', '\\"') for t in topics]
        topic_conds = " || ".join([f'topic == "{t}"' for t in safe_topics])
        conditions.append(f"({topic_conds})")
    if tags:
        safe_tags = [t.replace('"', '\\"') for t in tags]
        tag_conds = " || ".join([f'contains(tags, "{t}")' for t in safe_tags])
        conditions.append(f"({tag_conds})")
    if conditions:
        filter_expr = " && ".join(conditions)

    search_params = {"metric_type": "COSINE", "params": {"nprobe": 32}}
    dense_results = client.search(
        collection_name=_COLLECTION_NAME,
        data=[query_dense],
        limit=top_k * 3,
        output_fields=["id", "content", "file_path", "topic", "tags", "section_title"],
        search_params=search_params,
        filter=filter_expr,
    )

    if not dense_results or not dense_results[0]:
        return []

    sparse_index = _load_sparse_index(workspace)
    sparse_scores = _lexical_scores(query_sparse, sparse_index) if query_sparse and sparse_index else {}

    results_map = {}
    for hit in dense_results[0]:
        chunk_id = hit["entity"]["id"]
        dense_score = hit["distance"]
        sparse_score = sparse_scores.get(chunk_id, 0.0)
        combined = 0.7 * dense_score + 0.3 * sparse_score

        tags_val = hit["entity"].get("tags", "[]")
        try:
            tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
        except Exception:
            tags_list = []

        results_map[chunk_id] = {
            "id": chunk_id,
            "content": hit["entity"].get("content", ""),
            "file_path": hit["entity"].get("file_path", ""),
            "topic": hit["entity"].get("topic", ""),
            "tags": tags_list,
            "section_title": hit["entity"].get("section_title", ""),
            "dense_score": float(dense_score),
            "sparse_score": float(sparse_score),
            "score": float(combined),
        }

    stale_ids = []
    for chunk_id, sparse_score in sparse_scores.items():
        if chunk_id not in results_map and sparse_score > 0.3:
            try:
                lookup = client.query(
                    collection_name=_COLLECTION_NAME,
                    filter=f'id == "{chunk_id}"',
                    output_fields=["content", "file_path", "topic", "tags", "section_title"],
                    limit=1,
                )
                if lookup:
                    hit = lookup[0]
                    content = (hit.get("content") or "").strip()
                    if not content:
                        stale_ids.append(chunk_id)
                        continue
                    tags_val = hit.get("tags", "[]")
                    try:
                        tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                    except Exception:
                        tags_list = []
                    results_map[chunk_id] = {
                        "id": chunk_id,
                        "content": content,
                        "file_path": hit.get("file_path", ""),
                        "topic": hit.get("topic", ""),
                        "tags": tags_list,
                        "section_title": hit.get("section_title", ""),
                        "dense_score": 0.0,
                        "sparse_score": float(sparse_score),
                        "score": float(0.3 * sparse_score),
                    }
                else:
                    stale_ids.append(chunk_id)
            except Exception:
                pass

    if stale_ids:
        _purge_stale_sparse_ids(workspace, stale_ids)

    sorted_results = sorted(results_map.values(), key=lambda x: x["score"], reverse=True)
    return filter_usable_chunks(sorted_results)[:top_k]


def _hybrid_search_zvec(
    workspace: str,
    query_dense: list[float],
    query_sparse: dict,
    top_k: int = 10,
    topics: list = None,
    tags: list = None,
) -> list[dict]:
    import zvec

    collection = _open_zvec_collection(workspace)
    if collection is None:
        return []

    fetch_k = max(top_k * 10, top_k)
    try:
        docs = collection.query(
            zvec.Query(field_name="dense_vec", vector=query_dense),
            topk=fetch_k,
            output_fields=["content", "file_path", "topic", "tags", "section_title"],
        )
    except Exception as e:
        logger.warning(f"[rag/index] zvec query failed: {e}\n")
        return []

    results_map = {}
    for doc in docs:
        result = _zvec_doc_to_result(doc)
        if not _zvec_passes_filters(result, topics, tags):
            continue
        results_map[result["id"]] = result

    sparse_index = _load_sparse_index(workspace)
    sparse_scores = _lexical_scores(query_sparse, sparse_index) if query_sparse and sparse_index else {}
    stale_ids = []
    for chunk_id, sparse_score in sparse_scores.items():
        if chunk_id in results_map:
            dense_score = results_map[chunk_id].get("dense_score", 0.0)
            results_map[chunk_id]["sparse_score"] = float(sparse_score)
            results_map[chunk_id]["score"] = float(0.7 * dense_score + 0.3 * sparse_score)
            continue

        if sparse_score <= 0.3:
            continue
        lookup = _zvec_get_chunk_by_id(workspace, chunk_id)
        if not lookup:
            stale_ids.append(chunk_id)
            continue
        if not _zvec_passes_filters(lookup, topics, tags):
            continue
        content = (lookup.get("content") or "").strip()
        if not content:
            stale_ids.append(chunk_id)
            continue
        lookup["dense_score"] = 0.0
        lookup["sparse_score"] = float(sparse_score)
        lookup["score"] = float(0.3 * sparse_score)
        results_map[chunk_id] = lookup

    if stale_ids:
        _purge_stale_sparse_ids(workspace, stale_ids)

    sorted_results = sorted(results_map.values(), key=lambda x: x["score"], reverse=True)
    return filter_usable_chunks(sorted_results)[:top_k]


def _escape_filter_value(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _zvec_get_chunk_by_id(workspace: str, chunk_id: str) -> dict | None:
    import zvec

    collection = _open_zvec_collection(workspace)
    if collection is None:
        return None
    try:
        docs = collection.query(
            zvec.Query(field_name="dense_vec", id=chunk_id),
            topk=1,
            output_fields=["content", "file_path", "topic", "tags", "section_title"],
        )
    except Exception:
        return None
    if not docs:
        return None
    return _zvec_doc_to_result(docs[0])


def _zvec_chunks_by_file(
    workspace: str,
    file_path: str,
    limit: int = 10000,
    output_fields: list[str] | None = None,
) -> list[dict]:
    import zvec

    collection = _open_zvec_collection(workspace)
    if collection is None:
        return []
    query_output_fields = output_fields
    if output_fields == ["id"]:
        query_output_fields = ["file_path"]
    try:
        docs = collection.query(
            zvec.Query(field_name="dense_vec", vector=[1.0] + [0.0] * (_DENSE_DIM - 1)),
            topk=limit,
            filter=f'file_path = "{_zvec_escape(file_path)}"',
            output_fields=query_output_fields or ["content", "file_path", "topic", "tags", "section_title"],
        )
    except Exception as e:
        logger.warning(f"[rag/index] zvec query by file error: {e}\n")
        return []
    rows = []
    for doc in docs:
        if output_fields == ["id"]:
            rows.append({"id": doc.id})
        else:
            result = _zvec_doc_to_result(doc)
            rows.append({
                "id": result["id"],
                "content": result["content"],
                "file_path": result["file_path"],
                "topic": result["topic"],
                "section_title": result["section_title"],
            })
    return rows


def _get_chunks_by_file(workspace: str, file_path: str) -> list[dict]:
    if _use_zvec():
        return _zvec_chunks_by_file(workspace, file_path, output_fields=["id"])

    client = _get_client(workspace)
    if not _ensure_collection_loaded(workspace, client):
        return []
    try:
        safe_path = _escape_filter_value(file_path)
        results = client.query(
            collection_name=_COLLECTION_NAME,
            filter=f'file_path == "{safe_path}"',
            output_fields=["id"],
        )
        return results if results else []
    except Exception:
        return []


def fetch_chunks_by_file(workspace: str, file_path: str, limit: int = 2) -> list[dict]:
    """Return chunk payloads for a file (used by backlink context expansion)."""
    if _use_zvec():
        return _zvec_chunks_by_file(
            workspace,
            file_path,
            limit=limit,
            output_fields=["content", "file_path", "topic", "section_title"],
        )

    try:
        client = _get_client(workspace)
    except Exception as e:
        logger.warning(f"[rag/index] fetch_chunks_by_file client error: {e}\n")
        return []
    if not _ensure_collection_loaded(workspace, client):
        return []
    try:
        safe_path = _escape_filter_value(file_path)
        rows = client.query(
            collection_name=_COLLECTION_NAME,
            filter=f'file_path == "{safe_path}"',
            output_fields=["id", "content", "file_path", "topic", "section_title"],
            limit=limit,
        )
        return rows if rows else []
    except Exception as e:
        logger.warning(f"[rag/index] fetch_chunks_by_file error: {e}\n")
        return []


def delete_by_file(workspace: str, file_path: str):
    if _use_zvec():
        _delete_by_file_zvec(workspace, file_path)
        return

    client = _get_client(workspace)
    if not _ensure_collection_loaded(workspace, client):
        return

    chunks_to_check = _get_chunks_by_file(workspace, file_path)
    chunk_ids_to_remove = {c["id"] for c in chunks_to_check}

    try:
        safe_path = _escape_filter_value(file_path)
        client.delete(
            collection_name=_COLLECTION_NAME,
            filter=f'file_path == "{safe_path}"',
        )
    except Exception as e:
        logger.warning(f"[rag/index] delete_by_file error: {e}\n")

    sparse_index = _load_sparse_index(workspace)
    if _is_bm25_index(sparse_index):
        docs = sparse_index.get("docs", {})
        to_remove = [k for k in docs if k in chunk_ids_to_remove]
        for k in to_remove:
            del docs[k]
        if to_remove:
            _recompute_bm25_stats(sparse_index)
    else:
        to_remove = [k for k in sparse_index if k in chunk_ids_to_remove]
        for k in to_remove:
            del sparse_index[k]
    if to_remove:
        _sparse_index_path(workspace).write_text(json.dumps(sparse_index, ensure_ascii=False), encoding="utf-8")


def _delete_by_file_zvec(workspace: str, file_path: str):
    collection = _open_zvec_collection(workspace)
    if collection is None:
        return

    chunks_to_check = _zvec_chunks_by_file(workspace, file_path, output_fields=["id"])
    chunk_ids_to_remove = {c["id"] for c in chunks_to_check}

    try:
        collection.delete_by_filter(f'file_path = "{_zvec_escape(file_path)}"')
        collection.flush()
    except Exception as e:
        logger.warning(f"[rag/index] zvec delete_by_file error: {e}\n")

    sparse_index = _load_sparse_index(workspace)
    if _is_bm25_index(sparse_index):
        docs = sparse_index.get("docs", {})
        to_remove = [k for k in docs if k in chunk_ids_to_remove]
        for k in to_remove:
            del docs[k]
        if to_remove:
            _recompute_bm25_stats(sparse_index)
            _sparse_index_path(workspace).write_text(json.dumps(sparse_index, ensure_ascii=False), encoding="utf-8")
    else:
        to_remove = [k for k in sparse_index if k in chunk_ids_to_remove]
        for k in to_remove:
            del sparse_index[k]
        if to_remove:
            _sparse_index_path(workspace).write_text(json.dumps(sparse_index, ensure_ascii=False), encoding="utf-8")


def add_chunks(workspace: str, chunks: list[dict], embeddings: list[dict]):
    if _use_zvec():
        _add_chunks_zvec(workspace, chunks, embeddings)
        return

    client = _get_client(workspace)

    if not _collection_exists(client):
        _create_collection(client)

    data = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=False)):
        tags_str = json.dumps(chunk.get("tags", []), ensure_ascii=False)
        row = {
            "id": chunk.get("id", f"chunk_add_{i}"),
            "content": (chunk.get("content") or "")[:8192],
            "file_path": (chunk.get("file_path") or "")[:512],
            "topic": (chunk.get("topic") or "")[:256],
            "tags": tags_str[:1024],
            "section_title": (chunk.get("section_title") or "")[:256],
            "dense_vec": emb.get("dense_vec", [0.0] * _DENSE_DIM),
        }
        data.append(row)

    if data:
        client.insert(collection_name=_COLLECTION_NAME, data=data)
        _ensure_collection_loaded(workspace, client)

    _append_sparse_index(workspace, chunks, embeddings)


def _add_chunks_zvec(workspace: str, chunks: list[dict], embeddings: list[dict]):
    import zvec

    collection = _open_zvec_collection(workspace, create=True)

    docs = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=False)):
        tags_str = json.dumps(chunk.get("tags", []), ensure_ascii=False)
        docs.append(zvec.Doc(
            id=chunk.get("id", f"chunk_add_{i}"),
            vectors={"dense_vec": emb.get("dense_vec", [0.0] * _DENSE_DIM)},
            fields={
                "content": (chunk.get("content") or "")[:8192],
                "file_path": (chunk.get("file_path") or "")[:512],
                "topic": (chunk.get("topic") or "")[:256],
                "tags": tags_str[:1024],
                "section_title": (chunk.get("section_title") or "")[:256],
            },
        ))
    if docs:
        collection.insert(docs)
        collection.flush()

    _append_sparse_index(workspace, chunks, embeddings)


def _append_sparse_index(workspace: str, chunks: list[dict], embeddings: list[dict]):
    path = _sparse_index_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    new_index = _build_bm25_index(chunks, embeddings)
    if _is_bm25_index(existing):
        docs = existing.get("docs", {})
    else:
        docs = {}
        for chunk_id, lexical in existing.items():
            terms = _normalize_lexical_counts(lexical)
            docs[chunk_id] = {"terms": terms, "doc_len": float(sum(terms.values()))}

    docs.update(new_index.get("docs", {}))
    existing = _recompute_bm25_stats({"docs": docs})

    tmp_path = path.with_suffix('.tmp')
    tmp_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)
