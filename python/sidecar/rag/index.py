import json
from pathlib import Path

from pymilvus import DataType, MilvusClient

from utils.logger import logger

_COLLECTION_NAME = "noteai_chunks"
_DENSE_DIM = 512


def _db_path(workspace: str) -> str:
    p = Path(workspace) / ".rag_index" / "milvus_lite.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _get_client(workspace: str) -> MilvusClient:
    return MilvusClient(uri=_db_path(workspace))


def _collection_exists(client: MilvusClient) -> bool:
    return client.has_collection(_COLLECTION_NAME)


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
    try:
        client = _get_client(workspace)
        return _collection_exists(client)
    except Exception:
        return False


def build_index(workspace: str, chunks: list[dict], embeddings: list[dict], progress_callback=None):
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

    return {"success": True, "chunk_count": total}


def _sparse_index_path(workspace: str) -> Path:
    return Path(workspace) / ".rag_index" / "sparse_index.json"


def _save_sparse_index(workspace: str, chunks: list[dict], embeddings: list[dict]):
    path = _sparse_index_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)

    sparse_data = {}
    for chunk, emb in zip(chunks, embeddings, strict=False):
        chunk_id = chunk.get("id", "")
        lexical = emb.get("lexical_weights", {})
        if isinstance(lexical, dict):
            str_keys = {str(k): float(v) for k, v in lexical.items()}
            sparse_data[chunk_id] = str_keys

    path.write_text(json.dumps(sparse_data, ensure_ascii=False), encoding="utf-8")


def _load_sparse_index(workspace: str) -> dict:
    path = _sparse_index_path(workspace)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def hybrid_search(
    workspace: str,
    query_dense: list[float],
    query_sparse: dict,
    top_k: int = 10,
    topics: list = None,
    tags: list = None,
) -> list[dict]:
    client = _get_client(workspace)

    if not _collection_exists(client):
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
    sparse_scores = {}
    if query_sparse and sparse_index:
        query_norm = sum(v * v for v in query_sparse.values()) ** 0.5
        if query_norm > 0:
            for chunk_id, doc_sparse in sparse_index.items():
                dot = 0.0
                for k, v in query_sparse.items():
                    str_k = str(k)
                    if str_k in doc_sparse:
                        dot += v * doc_sparse[str_k]
                if dot > 0:
                    sparse_scores[chunk_id] = dot / query_norm

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

    for chunk_id, sparse_score in sparse_scores.items():
        if chunk_id not in results_map and sparse_score > 0.3:
            results_map[chunk_id] = {
                "id": chunk_id,
                "content": "",
                "file_path": "",
                "topic": "",
                "tags": [],
                "section_title": "",
                "dense_score": 0.0,
                "sparse_score": float(sparse_score),
                "score": float(0.3 * sparse_score),
            }

    sorted_results = sorted(results_map.values(), key=lambda x: x["score"], reverse=True)
    return sorted_results[:top_k]


def _get_chunks_by_file(workspace: str, file_path: str) -> list[dict]:
    client = _get_client(workspace)
    if not _collection_exists(client):
        return []
    try:
        results = client.query(
            collection_name=_COLLECTION_NAME,
            filter=f'file_path == "{file_path}"',
            output_fields=["id"],
        )
        return results if results else []
    except Exception:
        return []


def delete_by_file(workspace: str, file_path: str):
    client = _get_client(workspace)
    if not _collection_exists(client):
        return

    # 查询要删除的 chunk ID（在 delete 之前查询，避免最终一致性问题）
    chunks_to_check = _get_chunks_by_file(workspace, file_path)
    chunk_ids_to_remove = {c["id"] for c in chunks_to_check}

    try:
        client.delete(
            collection_name=_COLLECTION_NAME,
            filter=f'file_path == "{file_path}"',
        )
    except Exception as e:
        logger.warning(f"[rag/index] delete_by_file error: {e}\n")

    sparse_index = _load_sparse_index(workspace)
    to_remove = [k for k in sparse_index if k in chunk_ids_to_remove]
    for k in to_remove:
        del sparse_index[k]
    if to_remove:
        _sparse_index_path(workspace).write_text(json.dumps(sparse_index, ensure_ascii=False), encoding="utf-8")


def add_chunks(workspace: str, chunks: list[dict], embeddings: list[dict]):
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

    sparse_index = _load_sparse_index(workspace)
    for chunk, emb in zip(chunks, embeddings, strict=False):
        chunk_id = chunk.get("id", "")
        lexical = emb.get("lexical_weights", {})
        if isinstance(lexical, dict):
            str_keys = {str(k): float(v) for k, v in lexical.items()}
            sparse_index[chunk_id] = str_keys
    _sparse_index_path(workspace).write_text(json.dumps(sparse_index, ensure_ascii=False), encoding="utf-8")
