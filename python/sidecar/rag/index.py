"""Lightweight local RAG index using sqlite-vec + BM25s.

Schema:
- chunks: metadata table
- chunk_vectors: sqlite-vec virtual table for dense cosine search
- bm25s corpus + index files alongside the sqlite db
- metadata.json: topic/tag inverted indices for fast filtering
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import bm25s
import sqlite_vec

from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from utils.logger import logger

_COLLECTION_NAME = "noteai_chunks"
_DENSE_DIM = 512
_DENSE_METRIC = "cosine"
_BM25_K1 = 1.5
_BM25_B = 0.75

_lock = threading.Lock()


def _rag_index_dir(workspace: str) -> Path:
    return Path(workspace) / WORKSPACE_APP_FOLDER / RAG_INDEX_FOLDER


def _db_path(workspace: str) -> Path:
    p = _rag_index_dir(workspace) / "rag_index.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _bm25s_dir(workspace: str) -> Path:
    p = _rag_index_dir(workspace) / "bm25s"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _metadata_path(workspace: str) -> Path:
    return _rag_index_dir(workspace) / "metadata.json"


def _get_conn(workspace: str) -> sqlite3.Connection:
    db = _db_path(workspace)
    conn = sqlite3.connect(str(db), check_same_thread=False, timeout=30.0)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            file_path TEXT NOT NULL,
            topic TEXT,
            tags_json TEXT,
            section_title TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_path);
        CREATE INDEX IF NOT EXISTS idx_chunks_topic ON chunks(topic);
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
            rowid INTEGER PRIMARY KEY,
            embedding FLOAT[{_DENSE_DIM}]
        );
        """
    )


def is_usable_chunk(result: dict) -> bool:
    content = (result.get("content") or "").strip()
    return bool(content)


def filter_usable_chunks(results: list[dict]) -> list[dict]:
    return [r for r in results if is_usable_chunk(r)]


def index_exists(workspace: str) -> bool:
    return _db_path(workspace).exists() and _metadata_path(workspace).exists()


def _empty_metadata() -> dict[str, Any]:
    return {"topics": {}, "tags": {}, "files": {}, "version": 1}


def _load_metadata(workspace: str) -> dict[str, Any]:
    path = _metadata_path(workspace)
    if not path.exists():
        return _empty_metadata()
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
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


def build_index(workspace: str, chunks: list[dict], embeddings: list[dict], progress_callback=None) -> dict[str, Any]:
    index_dir = _rag_index_dir(workspace)
    index_dir.mkdir(parents=True, exist_ok=True)

    db = _db_path(workspace)
    if db.exists():
        db.unlink()
    for old in index_dir.glob("*.tmp"):
        old.unlink()

    conn = _get_conn(workspace)
    with conn:
        _ensure_schema(conn)
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM chunk_vectors")

        batch_size = 128
        total = len(chunks)
        dense_vecs: list[list[float]] = []
        chunk_ids: list[str] = []

        for i in range(0, total, batch_size):
            batch_chunks = chunks[i : i + batch_size]
            batch_embeds = embeddings[i : i + batch_size]

            rows = []
            vec_rows = []
            for chunk, emb in zip(batch_chunks, batch_embeds, strict=False):
                cid = chunk.get("id", f"chunk_{i}")
                content = (chunk.get("content") or "")[:8192]
                file_path = (chunk.get("file_path") or "")[:512]
                topic = (chunk.get("topic") or "")[:256]
                tags = chunk.get("tags") or []
                section_title = (chunk.get("section_title") or "")[:256]
                vec = emb.get("dense_vec") or [0.0] * _DENSE_DIM

                rows.append((cid, content, file_path, topic, json.dumps(tags, ensure_ascii=False), section_title))
                vec_rows.append((cid, json.dumps(vec, separators=(",", ":"))))
                dense_vecs.append(vec)
                chunk_ids.append(cid)

            conn.executemany(
                "INSERT INTO chunks (id, content, file_path, topic, tags_json, section_title) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.executemany(
                "INSERT INTO chunk_vectors (rowid, embedding) VALUES ((SELECT rowid FROM chunks WHERE id = ?), ?)",
                vec_rows,
            )

            if progress_callback:
                progress_callback(min(i + batch_size, total), total, "写入索引")

        # Build BM25s index
        if progress_callback:
            progress_callback(total, total, "构建 BM25 索引...")

        tokenized_corpus = bm25s.tokenize(
            [c.get("content", "") for c in chunks],
            stopwords="zh",
        )
        retriever = bm25s.BM25(corpus=chunks, k1=_BM25_K1, b=_BM25_B)
        retriever.index(tokenized_corpus)
        retriever.save(_bm25s_dir(workspace), corpus=chunks)

        # Build metadata indices
        metadata = _empty_metadata()
        for chunk in chunks:
            _update_metadata_index(metadata, chunk, mode="add")
        _save_metadata(workspace, metadata)

    return {"success": True, "chunk_count": total}


def add_chunks(workspace: str, chunks: list[dict], embeddings: list[dict]) -> None:
    if not chunks:
        return

    conn = _get_conn(workspace)
    metadata = _load_metadata(workspace)

    with conn:
        _ensure_schema(conn)

        rows = []
        vec_rows = []
        for chunk, emb in zip(chunks, embeddings, strict=False):
            cid = chunk.get("id", "")
            if not cid:
                continue
            content = (chunk.get("content") or "")[:8192]
            file_path = (chunk.get("file_path") or "")[:512]
            topic = (chunk.get("topic") or "")[:256]
            tags = chunk.get("tags") or []
            section_title = (chunk.get("section_title") or "")[:256]
            vec = emb.get("dense_vec") or [0.0] * _DENSE_DIM

            rows.append((cid, content, file_path, topic, json.dumps(tags, ensure_ascii=False), section_title))
            vec_rows.append((cid, json.dumps(vec, separators=(",", ":"))))
            _update_metadata_index(metadata, chunk, mode="add")

        if not rows:
            return

        conn.executemany(
            "INSERT OR REPLACE INTO chunks (id, content, file_path, topic, tags_json, section_title) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO chunk_vectors (rowid, embedding) VALUES ((SELECT rowid FROM chunks WHERE id = ?), ?)",
            vec_rows,
        )

    _save_metadata(workspace, metadata)

    # Rebuild BM25s with merged corpus
    try:
        bm25_dir = _bm25s_dir(workspace)
        if bm25_dir.exists() and any(bm25_dir.iterdir()):
            old_retriever = bm25s.BM25.load(bm25_dir, load_corpus=True)
            old_corpus = old_retriever.corpus
            if isinstance(old_corpus, dict):
                old_corpus = old_corpus.get("documents", [])
        else:
            old_corpus = []

        merged_corpus = list(old_corpus) + [c for c in chunks if c.get("id")]
        tokenized = bm25s.tokenize([c.get("content", "") for c in merged_corpus], stopwords="zh")
        retriever = bm25s.BM25(corpus=merged_corpus, k1=_BM25_K1, b=_BM25_B)
        retriever.index(tokenized)
        retriever.save(bm25_dir, corpus=merged_corpus)
    except Exception as e:
        logger.warning(f"[rag/index] BM25s rebuild failed: {e}\n")


def delete_by_file(workspace: str, file_path: str) -> None:
    conn = _get_conn(workspace)
    metadata = _load_metadata(workspace)

    with conn:
        _ensure_schema(conn)
        cur = conn.execute(
            "SELECT id, content, file_path, topic, tags_json, section_title FROM chunks WHERE file_path = ?",
            (file_path,),
        )
        removed = []
        for row in cur.fetchall():
            tags = []
            try:
                tags = json.loads(row["tags_json"] or "[]")
            except Exception:
                pass
            chunk = {
                "id": row["id"],
                "content": row["content"],
                "file_path": row["file_path"],
                "topic": row["topic"],
                "tags": tags,
                "section_title": row["section_title"],
            }
            removed.append(chunk)
            _update_metadata_index(metadata, chunk, mode="remove")

        if removed:
            ids = tuple(c["id"] for c in removed)
            conn.execute(
                f"DELETE FROM chunk_vectors WHERE rowid IN (SELECT rowid FROM chunks WHERE id IN ({','.join('?' * len(ids))}))",
                ids,
            )
            conn.execute(
                f"DELETE FROM chunks WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )

    _save_metadata(workspace, metadata)

    # Rebuild BM25s without deleted docs
    try:
        bm25_dir = _bm25s_dir(workspace)
        if not bm25_dir.exists() or not any(bm25_dir.iterdir()):
            return
        retriever = bm25s.BM25.load(bm25_dir, load_corpus=True)
        old_corpus = retriever.corpus
        if isinstance(old_corpus, dict):
            old_corpus = old_corpus.get("documents", [])
        removed_ids = {c["id"] for c in removed}
        new_corpus = [c for c in old_corpus if c.get("id") not in removed_ids]
        if not new_corpus:
            for f in bm25_dir.iterdir():
                f.unlink()
            return
        tokenized = bm25s.tokenize([c.get("content", "") for c in new_corpus], stopwords="zh")
        new_retriever = bm25s.BM25(corpus=new_corpus, k1=_BM25_K1, b=_BM25_B)
        new_retriever.index(tokenized)
        new_retriever.save(bm25_dir, corpus=new_corpus)
    except Exception as e:
        logger.warning(f"[rag/index] BM25s rebuild after delete failed: {e}\n")


def _load_bm25_retriever(workspace: str):
    bm25_dir = _bm25s_dir(workspace)
    if not bm25_dir.exists() or not any(bm25_dir.iterdir()):
        return None, []
    try:
        retriever = bm25s.BM25.load(bm25_dir, load_corpus=True)
        corpus = retriever.corpus
        if isinstance(corpus, dict):
            corpus = corpus.get("documents", [])
        return retriever, corpus
    except Exception:
        return None, []


def _dense_search(
    conn: sqlite3.Connection,
    query_dense: list[float],
    candidate_ids: set[str] | None,
    top_k: int,
) -> list[dict]:
    if candidate_ids is not None and not candidate_ids:
        return []

    # sqlite-vec KNN
    vec_json = json.dumps(query_dense, separators=(",", ":"))
    sql = """
        SELECT c.id, c.content, c.file_path, c.topic, c.tags_json, c.section_title,
               cv.distance AS dense_score
        FROM chunk_vectors AS cv
        JOIN chunks AS c ON c.rowid = cv.rowid
        WHERE cv.embedding MATCH ? AND cv.k = ?
    """
    params: list[Any] = [vec_json, top_k * 4]

    if candidate_ids:
        placeholders = ",".join("?" * len(candidate_ids))
        sql += f" AND c.id IN ({placeholders})"
        params.extend(list(candidate_ids))

    sql += " ORDER BY cv.distance ASC"

    rows = conn.execute(sql, params).fetchall()
    results = []
    for row in rows:
        tags = []
        try:
            tags = json.loads(row["tags_json"] or "[]")
        except Exception:
            pass
        # sqlite-vec cosine distance -> score
        distance = float(row["dense_score"])
        score = 1.0 - distance
        results.append(
            {
                "id": row["id"],
                "content": row["content"],
                "file_path": row["file_path"],
                "topic": row["topic"],
                "tags": tags,
                "section_title": row["section_title"],
                "dense_vec": None,
                "dense_score": score,
                "sparse_score": 0.0,
                "score": score,
            }
        )
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
    conn = _get_conn(workspace)
    _ensure_schema(conn)

    candidates = _filter_candidates(workspace, topics, tags)

    dense_results = _dense_search(conn, query_dense, candidates, top_k)
    dense_map = {r["id"]: r for r in dense_results}

    # Use query_text for BM25; fallback to reconstructing from sparse dict
    if not query_text and query_sparse:
        query_text = " ".join(str(k) for k, v in query_sparse.items() if v > 0)

    sparse_scores: dict[str, float] = {}
    if query_text:
        sparse_scores = _sparse_search(workspace, query_text, candidates, top_k)

    # Merge dense + sparse
    results_map = {}
    for cid, r in dense_map.items():
        sparse = sparse_scores.get(cid, 0.0)
        r["sparse_score"] = sparse
        r["score"] = 0.7 * r["dense_score"] + 0.3 * min(sparse, 1.0)
        results_map[cid] = r

    # Add sparse-only hits
    for cid, sparse in sparse_scores.items():
        if cid in results_map:
            continue
        row = conn.execute(
            "SELECT id, content, file_path, topic, tags_json, section_title FROM chunks WHERE id = ?", (cid,)
        ).fetchone()
        if not row:
            continue
        tags = []
        try:
            tags = json.loads(row["tags_json"] or "[]")
        except Exception:
            pass
        results_map[cid] = {
            "id": row["id"],
            "content": row["content"],
            "file_path": row["file_path"],
            "topic": row["topic"],
            "tags": tags,
            "section_title": row["section_title"],
            "dense_vec": None,
            "dense_score": 0.0,
            "sparse_score": sparse,
            "score": 0.3 * min(sparse, 1.0),
        }

    sorted_results = sorted(results_map.values(), key=lambda x: x["score"], reverse=True)
    return filter_usable_chunks(sorted_results)[:top_k]


def _get_chunks_by_file(workspace: str, file_path: str) -> list[dict]:
    conn = _get_conn(workspace)
    _ensure_schema(conn)
    try:
        rows = conn.execute("SELECT id FROM chunks WHERE file_path = ?", (file_path,)).fetchall()
        return [{"id": row["id"]} for row in rows]
    except Exception:
        return []


def fetch_chunks_by_file(workspace: str, file_path: str, limit: int = 2) -> list[dict]:
    try:
        conn = _get_conn(workspace)
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT id, content, file_path, topic, section_title FROM chunks WHERE file_path = ? LIMIT ?",
            (file_path, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"[rag/index] fetch_chunks_by_file error: {e}\n")
        return []
