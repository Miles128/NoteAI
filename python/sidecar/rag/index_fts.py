"""zvec 内置 FTS（jieba）稀疏检索与索引重建。

替代原来的 bm25s：词法索引和向量共存于同一个 zvec collection，
少一个依赖、少一份索引、少一条重建路径。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sidecar.rag.index_core import (
    _FETCH_BATCH_SIZE,
    _empty_metadata,
    _ensure_fts_index,
    _get_collection,
    _save_metadata,
    _tags_from_fields,
    _update_metadata_index,
)
from sidecar.rag.lazy import lazy_import
from utils.logger import logger

if TYPE_CHECKING:
    import zvec
else:
    zvec = lazy_import("zvec")


def normalize_sparse_scores(scores: dict[str, float]) -> dict[str, float]:
    """min-max 归一化到 0..1，供 dense/sparse 加权融合。"""
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return dict.fromkeys(scores, 1.0)
    return {key: (value - lo) / (hi - lo) for key, value in scores.items()}


def fts_search(
    collection: zvec.Collection,
    query_text: str,
    top_k: int,
    candidate_ids: set[str] | None = None,
) -> dict[str, float]:
    """返回 ``chunk_id -> 原始 FTS 分数``（未归一化）。"""
    if not query_text:
        return {}
    query = zvec.Query(
        field_name="content",
        fts=zvec.Fts(match_string=query_text),
    )
    # 与 dense 一致：候选集过滤在应用层做，多取一些再筛
    search_topk = top_k * 4
    if candidate_ids:
        search_topk = max(search_topk, min(len(candidate_ids), 10000))
    docs = collection.query(query, topk=search_topk, output_fields=[])
    out: dict[str, float] = {}
    for doc in docs:
        if candidate_ids is not None and doc.id not in candidate_ids:
            continue
        out[doc.id] = float(doc.score or 0.0)
    return out


def rebuild_search_indices(
    workspace: str,
    all_chunk_ids: list[str],
    progress_callback=None,
    collection: zvec.Collection | None = None,
) -> int:
    """从 zvec collection 重建 metadata 与 FTS 索引。"""
    if collection is None:
        collection = _get_collection(workspace)

    corpus: list[dict] = []
    batch_size = _FETCH_BATCH_SIZE
    total = len(all_chunk_ids)
    for offset in range(0, total, batch_size):
        batch = all_chunk_ids[offset : offset + batch_size]
        fetched = collection.fetch(
            batch,
            output_fields=["content", "file_path", "topic", "tags_json", "section_title"],
            include_vector=False,
        )
        for chunk_id, doc in fetched.items():
            fields = doc.fields or {}
            corpus.append(
                {
                    "id": chunk_id,
                    "content": fields.get("content", ""),
                    "file_path": fields.get("file_path", ""),
                    "topic": fields.get("topic", ""),
                    "tags": _tags_from_fields(fields),
                    "section_title": fields.get("section_title", ""),
                }
            )
        if progress_callback:
            progress_callback(min(offset + batch_size, total), total, "重建检索索引")

    if not corpus:
        return 0

    metadata = _empty_metadata()
    for chunk in corpus:
        _update_metadata_index(metadata, chunk, mode="add")
    _save_metadata(workspace, metadata)

    if progress_callback:
        progress_callback(total, total, "重建 FTS 索引")
    try:
        _ensure_fts_index(workspace, collection, force=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[rag/index] FTS 索引重建失败: {exc}\n")

    return len(corpus)
