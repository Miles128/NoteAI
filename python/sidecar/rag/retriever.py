import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from config import config, is_ignored_dir
from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from utils.error_handler import log_exception
from utils.logger import logger
from utils.ttl_cache import TTLCache

DEFAULT_TOP_K = 5
SEARCH_TOP_K_TAGS = 7
HYDE_TRIGGER_BELOW_SCORE = 0.33
_MMR_CANDIDATE_CAP = 10
_RERANK_CANDIDATE_CAP = 5
_SKIP_RERANK_SCORE = 0.75
_RERANK_MAX_CHARS = 512
_FETCH_BATCH_SIZE = 256

_RERANKER = None
_RERANKER_DISABLED_UNTIL: float = 0.0
_RERANKER_COOLDOWN_SECONDS = 60
_RERANKER_LOCK = threading.Lock()

_RETRIEVE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag_retrieve")

# TTL cache for identical queries: key -> (expanded_results, citations)
# Entries expire after 5 minutes so content updates are reflected quickly.
_query_cache = TTLCache(ttl=300, max_size=50)


def _reranker_enabled() -> bool:
    if os.environ.get("NOTEAI_DISABLE_RERANKER", "").lower() in ("1", "true", "yes"):
        return False
    return True


def _get_reranker():
    global _RERANKER, _RERANKER_DISABLED_UNTIL

    if not _reranker_enabled():
        return None
    if time.time() < _RERANKER_DISABLED_UNTIL:
        return None
    if _RERANKER is not None:
        return _RERANKER
    with _RERANKER_LOCK:
        if time.time() < _RERANKER_DISABLED_UNTIL:
            return None
        if _RERANKER is not None:
            return _RERANKER
        try:
            from config.constants import SYSTEM_APP_DATA_DIR
            from sidecar.rag.embedder import _ensure_hf_env

            _ensure_hf_env()
            from FlagEmbedding import FlagReranker

            _hf_cache = SYSTEM_APP_DATA_DIR / "hf_hub"
            _hf_cache.mkdir(parents=True, exist_ok=True)
            _RERANKER = FlagReranker(
                "BAAI/bge-reranker-v2-m3",
                use_fp16=True,
                cache_dir=str(_hf_cache),
                batch_size=64,
            )
            return _RERANKER
        except Exception as e:
            _RERANKER_DISABLED_UNTIL = time.time() + _RERANKER_COOLDOWN_SECONDS
            logger.warning(f"[rag/retriever] reranker unavailable, cooling down for {_RERANKER_COOLDOWN_SECONDS}s: {e}\n")
            return None


def _cache_key(query: str, topics, tags) -> str:
    ws = config.workspace_path or ""
    return f"{ws}||{query}||{','.join(sorted(topics or []))}||{','.join(sorted(tags or []))}"


def _get_cached(query: str, topics, tags):
    key = _cache_key(query, topics, tags)
    return _query_cache.get(key)


def _set_cached(query: str, topics, tags, value):
    key = _cache_key(query, topics, tags)
    _query_cache.set(key, value)


def retrieve(query: str, topics: list = None, tags: list = None, progress_callback=None) -> list:
    workspace = config.workspace_path
    if not workspace:
        return []

    cached = _get_cached(query, topics, tags)
    if cached is not None:
        return cached[0]

    from sidecar.rag.embedder import encode_query
    from sidecar.rag.index import filter_usable_chunks, hybrid_search

    query_emb = encode_query(query)
    if not query_emb.get("dense_vec"):
        return []

    top_k = SEARCH_TOP_K_TAGS if (topics or tags) else DEFAULT_TOP_K

    # Profile rewrite runs in parallel (pure LLM call) but is only used as fallback.
    profile_future = _RETRIEVE_EXECUTOR.submit(_rewrite_profile, query)

    results = hybrid_search(
        workspace,
        query_dense=query_emb["dense_vec"],
        query_sparse=query_emb.get("lexical_weights", {}),
        query_text=query,
        top_k=top_k,
        topics=topics,
        tags=tags,
    )

    # HyDE only if the original search is weak, avoiding a mandatory LLM call.
    if not results or results[0].get("score", 0) < HYDE_TRIGGER_BELOW_SCORE:
        try:
            hyde_results = _hyde_search(workspace, query, topics, tags, progress_callback)
            if hyde_results:
                existing_ids = {r.get("id") for r in results}
                for r in hyde_results:
                    if r.get("id") not in existing_ids:
                        results.append(r)
                        existing_ids.add(r.get("id"))
                results.sort(key=lambda x: x.get("score", 0), reverse=True)
                results = results[:top_k]
        except Exception as e:
            log_exception("[rag/retriever] HyDE search failed", e, level="debug", logger=logger)

    # Profile fallback only if main search returned nothing.
    profile_query = profile_future.result()
    if not results and profile_query != query:
        profile_emb = encode_query(profile_query)
        if profile_emb.get("dense_vec"):
            results = hybrid_search(
                workspace,
                query_dense=profile_emb["dense_vec"],
                query_sparse=profile_emb.get("lexical_weights", {}),
                query_text=profile_query,
                top_k=top_k,
                topics=topics,
                tags=tags,
            )

    if len(results) > _MMR_CANDIDATE_CAP:
        results = results[:_MMR_CANDIDATE_CAP]

    if len(results) >= 2:
        results = _mmr_dedup(results, top_k=DEFAULT_TOP_K)

    if len(results) >= 2:
        results = _rerank(query, results[:_RERANK_CANDIDATE_CAP], top_k=DEFAULT_TOP_K)

    results = filter_usable_chunks(results)[:DEFAULT_TOP_K]

    from sidecar.rag.context_expand import expand_retrieval_context

    expanded = expand_retrieval_context(results, topics=topics, workspace=workspace)
    expanded = filter_usable_chunks(expanded)

    _set_cached(query, topics, tags, (expanded, []))
    return expanded


def _rewrite_profile(query: str) -> str:
    try:
        from sidecar.rag.profile import rewrite_query_with_profile

        return rewrite_query_with_profile(query)
    except Exception as e:
        log_exception("[rag/retriever] profile rewrite failed", e, level="debug", logger=logger)
        return query


def _hyde_search(workspace, query, topics, tags, progress_callback=None) -> list:
    try:
        from prompts import HYDE_PROMPT
        from utils.llm_utils import create_llm

        prompt = HYDE_PROMPT.format(query=query)
        llm = create_llm(temperature=0.3)
        result = llm.invoke(prompt)
        hypo_answer = result.content if hasattr(result, "content") else str(result)

        from sidecar.rag.embedder import encode_query
        from sidecar.rag.index import hybrid_search

        hyde_emb = encode_query(hypo_answer)
        if not hyde_emb.get("dense_vec"):
            return []

        return hybrid_search(
            workspace,
            query_dense=hyde_emb["dense_vec"],
            query_sparse=hyde_emb.get("lexical_weights", {}),
            query_text=hypo_answer,
            top_k=DEFAULT_TOP_K,
            topics=topics,
            tags=tags,
        )
    except Exception as e:
        logger.warning(f"[rag/retriever] HyDE search error: {e}\n")
        return []


def _mmr_dedup(results: list, top_k: int = 5, lambda_param: float = 0.5) -> list:
    if len(results) <= top_k:
        return results

    import numpy as np

    try:
        dense_vecs = []
        needs_encode = False
        for r in results:
            vec = r.get("dense_vec")
            if vec and len(vec) == 512:
                dense_vecs.append(vec)
            else:
                needs_encode = True
                break

        if needs_encode or not dense_vecs:
            from sidecar.rag.embedder import encode

            contents = [r.get("content", "") for r in results]
            if not any(contents):
                return results[:top_k]

            embeddings = encode(contents)
            dense_vecs_arr = embeddings["dense_vecs"]
        else:
            dense_vecs_arr = np.array(dense_vecs, dtype=np.float32)

        norms = np.linalg.norm(dense_vecs_arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        norm_vecs = dense_vecs_arr / norms

        selected_indices = [0]
        remaining = set(range(1, len(results)))

        while len(selected_indices) < top_k and remaining:
            best_idx = -1
            best_score = -float("inf")

            for idx in remaining:
                relevance = results[idx].get("score", 0)
                max_sim = 0.0
                for sel_idx in selected_indices:
                    sim = float(np.dot(norm_vecs[idx], norm_vecs[sel_idx]))
                    max_sim = max(max_sim, sim)

                mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx

            if best_idx >= 0:
                selected_indices.append(best_idx)
                remaining.discard(best_idx)
            else:
                break

        return [results[i] for i in selected_indices]
    except Exception as e:
        logger.warning(f"[rag/retriever] MMR dedup error: {e}\n")
        return results[:top_k]


def _rerank(query: str, results: list, top_k: int = 5) -> list:
    try:
        if len(results) <= 1:
            return results[:top_k]

        # Skip reranking if the top result is already very strong
        if results and results[0].get("score", 0) >= _SKIP_RERANK_SCORE:
            return results[:top_k]

        reranker = _get_reranker()
        if reranker is None:
            return results[:top_k]

        scored = [(r, (r.get("content") or "")[:_RERANK_MAX_CHARS]) for r in results if r.get("content")]
        if not scored:
            return results[:top_k]

        pairs = [[query, text] for _, text in scored]
        scores = reranker.compute_score(pairs, normalize=True)
        if isinstance(scores, float):
            scores = [scores]

        for (row, _), score in zip(scored, scores, strict=False):
            row["rerank_score"] = float(score)

        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return results[:top_k]
    except ImportError:
        return results[:top_k]
    except Exception as e:
        logger.warning(f"[rag/retriever] rerank error: {e}\n")
        return results[:top_k]


def _excluded_dirs() -> set[str]:
    return {
        ".git",
        ".obsidian",
        ".trash",
        ".rag_index",
        ".ai_memory",
        "Raw",
        WORKSPACE_APP_FOLDER,
        RAG_INDEX_FOLDER,
    }


def _scan_files(workspace_path: Path):
    """Scan workspace for markdown files eligible for indexing."""
    excluded_dirs = _excluded_dirs()
    files: dict[str, dict] = {}
    for md_file in sorted(workspace_path.rglob("*.md")):
        if md_file.name.startswith("."):
            continue
        if "wiki" in md_file.parts:
            continue
        if any(p.name in excluded_dirs or is_ignored_dir(p.name) for p in md_file.relative_to(workspace_path).parents):
            continue
        if md_file.name.endswith("_综述.md") or md_file.name.endswith("综述.md"):
            continue

        stat = md_file.stat()
        rel = str(md_file.relative_to(workspace_path))
        files[rel] = {"mtime": stat.st_mtime, "size": stat.st_size}
    return files


def is_index_up_to_date(workspace: str | None = None) -> bool:
    """Check whether the existing RAG index matches current workspace files."""
    workspace = workspace or config.workspace_path
    if not workspace:
        return False
    from sidecar.rag.index import index_exists, load_manifest

    if not index_exists(workspace):
        return False
    wp = Path(workspace)
    current_files = _scan_files(wp)
    manifest = load_manifest(workspace).get("files", {})
    if set(current_files.keys()) != set(manifest.keys()):
        return False
    for rel, info in current_files.items():
        old = manifest.get(rel, {})
        if old.get("mtime") != info["mtime"] or old.get("size") != info["size"]:
            return False
    return True


def _chunk_files_parallel(workspace_path: Path, rel_paths: list[str]) -> list[dict]:
    """Read and chunk a list of files in parallel."""
    from sidecar.rag.chunker import chunk_file

    def _chunk_one(rel_path: str) -> list[dict]:
        try:
            text = (workspace_path / rel_path).read_text(encoding="utf-8")
            return chunk_file(rel_path, text)
        except Exception as e:
            logger.warning(f"[rag/retriever] chunk error {rel_path}: {e}\n")
            return []

    all_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="rag_chunk") as executor:
        for chunks in executor.map(_chunk_one, rel_paths):
            all_chunks.extend(chunks)
    return all_chunks


def _full_rebuild(workspace: str, workspace_path: Path, current_files: dict[str, dict], progress_callback=None):
    """Full rebuild path used when incremental rebuild is not possible."""
    from sidecar.rag.chunker import chunk_file
    from sidecar.rag.embedder import build_and_save_global_idf, encode_documents
    from sidecar.rag.index import build_index, rebuild_search_indices, save_manifest
    from sidecar.rag.profile import update_profile_from_topics

    rel_paths = sorted(current_files.keys())
    all_chunks: list[dict] = []
    for rel_path in rel_paths:
        try:
            text = (workspace_path / rel_path).read_text(encoding="utf-8")
            all_chunks.extend(chunk_file(rel_path, text))
        except Exception as e:
            logger.warning(f"[rag/retriever] chunk error {rel_path}: {e}\n")

    if not all_chunks:
        return {"success": False, "message": "未找到可索引的文件"}

    if progress_callback:
        progress_callback(0, len(all_chunks), "正在生成 Embedding...")

    texts = [c["content"] for c in all_chunks]
    try:
        embeddings = encode_documents(
            texts,
            download_callback=lambda msg: progress_callback(0, 1, msg) if progress_callback else None,
            progress_callback=progress_callback,
        )
    except Exception as e:
        return {"success": False, "message": f"Embedding 生成失败: {e}"}

    if progress_callback:
        progress_callback(len(all_chunks) // 2, len(all_chunks), "正在构建索引...")

    build_index(workspace, all_chunks, embeddings, progress_callback=progress_callback)

    # Build search indices and manifest from the new collection
    all_chunk_ids = [c["id"] for c in all_chunks]
    chunk_count = rebuild_search_indices(workspace, all_chunk_ids, progress_callback=progress_callback)
    build_and_save_global_idf(all_chunks, workspace)

    manifest = {"version": 1, "files": {}}
    for c in all_chunks:
        rel = c["file_path"]
        entry = manifest["files"].setdefault(rel, {"mtime": current_files[rel]["mtime"], "size": current_files[rel]["size"], "chunks": []})
        entry["chunks"].append(c["id"])
    save_manifest(workspace, manifest)

    topic_counts = {}
    for c in all_chunks:
        t = c.get("topic", "")
        if t:
            topic_counts[t] = topic_counts.get(t, 0) + 1
    sorted_topics = sorted(topic_counts.keys(), key=lambda x: topic_counts[x], reverse=True)
    update_profile_from_topics(sorted_topics)

    return {"success": True, "chunk_count": chunk_count}


def rebuild_index(progress_callback=None, *, force_full: bool = False, workspace: str | None = None):
    workspace = workspace or config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    from sidecar.rag.embedder import build_and_save_global_idf, encode_documents
    from sidecar.rag.index import (
        add_chunks,
        delete_by_file,
        index_exists,
        load_manifest,
        rebuild_search_indices,
        save_manifest,
    )
    from sidecar.rag.profile import update_profile_from_topics

    workspace_path = Path(workspace)
    current_files = _scan_files(workspace_path)

    if not current_files:
        return {"success": False, "message": "未找到可索引的文件"}

    manifest = load_manifest(workspace)
    can_incremental = (
        not force_full
        and index_exists(workspace)
        and manifest.get("files")
    )

    if not can_incremental:
        if progress_callback:
            progress_callback(0, len(current_files), "全量重建索引...")
        return _full_rebuild(workspace, workspace_path, current_files, progress_callback=progress_callback)

    # Incremental rebuild
    old_files = manifest.get("files", {})
    unchanged: list[str] = []
    modified: list[str] = []
    new_files: list[str] = []

    for rel, info in current_files.items():
        old = old_files.get(rel)
        if old and old.get("mtime") == info["mtime"] and old.get("size") == info["size"]:
            unchanged.append(rel)
        else:
            modified.append(rel)

    deleted = [rel for rel in old_files if rel not in current_files]

    if progress_callback:
        progress_callback(0, max(len(modified) + len(new_files) + len(deleted), 1), "准备增量更新...")

    # Delete removed and modified files from the collection.
    # Reuse a single opened collection and defer BM25s rebuild to the end
    # because zvec.open() reloads the mmindex every time and is expensive.
    from sidecar.rag.index import _get_collection

    collection = _get_collection(workspace)
    for rel_path in deleted + modified:
        try:
            delete_by_file(workspace, rel_path, collection=collection, rebuild_bm25s=False)
        except Exception as e:
            logger.warning(f"[rag/retriever] delete_by_file failed {rel_path}: {e}\n")

    # Chunk new and modified files in parallel
    files_to_chunk = modified + new_files
    new_chunks: list[dict] = []
    if files_to_chunk:
        new_chunks = _chunk_files_parallel(workspace_path, files_to_chunk)

    # Encode and add new chunks
    if new_chunks:
        if progress_callback:
            progress_callback(0, len(new_chunks), "正在生成 Embedding...")
        texts = [c["content"] for c in new_chunks]
        try:
            embeddings = encode_documents(
                texts,
                download_callback=lambda msg: progress_callback(0, 1, msg) if progress_callback else None,
                progress_callback=progress_callback,
            )
        except Exception as e:
            return {"success": False, "message": f"Embedding 生成失败: {e}"}
        add_chunks(workspace, new_chunks, embeddings)

    # Rebuild BM25s, metadata, global IDF from the full collection
    all_chunk_ids: list[str] = []
    new_manifest = {"version": 1, "files": {}}

    for rel in unchanged:
        entry = old_files[rel]
        chunk_ids = entry.get("chunks", [])
        all_chunk_ids.extend(chunk_ids)
        new_manifest["files"][rel] = {
            "mtime": entry["mtime"],
            "size": entry["size"],
            "chunks": chunk_ids,
        }

    for c in new_chunks:
        rel = c["file_path"]
        all_chunk_ids.append(c["id"])
        entry = new_manifest["files"].setdefault(
            rel,
            {"mtime": current_files[rel]["mtime"], "size": current_files[rel]["size"], "chunks": []},
        )
        entry["chunks"].append(c["id"])

    chunk_count = rebuild_search_indices(
        workspace, all_chunk_ids, progress_callback=progress_callback, collection=collection
    )

    # Build global IDF from full corpus
    full_corpus: list[dict] = []
    if collection is not None:
        from sidecar.rag.index import _tags_from_fields

        batch_size = _FETCH_BATCH_SIZE
        for i in range(0, len(all_chunk_ids), batch_size):
            batch = all_chunk_ids[i : i + batch_size]
            fetched = collection.fetch(
                batch,
                output_fields=["content", "file_path", "topic", "tags_json", "section_title"],
                include_vector=False,
            )
            for doc in fetched.values():
                fields = doc.fields or {}
                full_corpus.append(
                    {
                        "id": doc.id,
                        "content": fields.get("content", ""),
                        "file_path": fields.get("file_path", ""),
                        "topic": fields.get("topic", ""),
                        "tags": _tags_from_fields(fields),
                        "section_title": fields.get("section_title", ""),
                    }
                )
    else:
        full_corpus = new_chunks

    build_and_save_global_idf(full_corpus, workspace)
    save_manifest(workspace, new_manifest)

    topic_counts = {}
    for c in full_corpus:
        t = c.get("topic", "")
        if t:
            topic_counts[t] = topic_counts.get(t, 0) + 1
    sorted_topics = sorted(topic_counts.keys(), key=lambda x: topic_counts[x], reverse=True)
    update_profile_from_topics(sorted_topics)

    return {"success": True, "chunk_count": chunk_count, "incremental": True}


def incremental_update(file_path: str, action: str = "update"):
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    from sidecar.rag.chunker import chunk_file
    from sidecar.rag.embedder import encode_documents
    from sidecar.rag.index import add_chunks, delete_by_file

    p = Path(file_path)
    if not p.exists():
        p = Path(workspace) / file_path
    if not p.exists():
        return {"success": False, "message": f"文件不存在: {file_path}"}

    rel_path = str(p.relative_to(workspace))

    if action in ("update", "delete"):
        delete_by_file(workspace, rel_path)

    if action in ("update", "add"):
        try:
            text = p.read_text(encoding="utf-8")
            chunks = chunk_file(rel_path, text)
            if chunks:
                texts = [c["content"] for c in chunks]
                embeddings = encode_documents(texts)
                add_chunks(workspace, chunks, embeddings)
            return {"success": True, "chunk_count": len(chunks)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    return {"success": True}
