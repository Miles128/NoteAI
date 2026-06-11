import os
import sys
import threading
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from config.constants import SYSTEM_APP_DATA_DIR
from config import config, is_ignored_dir
from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from utils.logger import logger

DEFAULT_TOP_K = 5
# 单次查询：控制 Milvus 召回量、减少 MMR 内 batch-embed 与 cross-encoder 对数
SEARCH_TOP_K_TAGS = 7
# best hit 低于该阈值才走 HyDE（省一次 LLM）
HYDE_TRIGGER_BELOW_SCORE = 0.33
_MMR_CANDIDATE_CAP = 10
_RERANK_CANDIDATE_CAP = 6

_RERANKER = None
_RERANKER_DISABLED = False
_RERANKER_LOCK = threading.Lock()


def _reranker_enabled() -> bool:
    if os.environ.get("NOTEAI_DISABLE_RERANKER", "").lower() in ("1", "true", "yes"):
        return False
    if os.environ.get("NOTEAI_ENABLE_RERANKER", "").lower() in ("1", "true", "yes"):
        return True
    return True


def _get_reranker():
    global _RERANKER, _RERANKER_DISABLED
    if not _reranker_enabled():
        return None
    if _RERANKER_DISABLED:
        return None
    if _RERANKER is not None:
        return _RERANKER
    with _RERANKER_LOCK:
        if _RERANKER_DISABLED:
            return None
        if _RERANKER is not None:
            return _RERANKER
        try:
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
            _RERANKER_DISABLED = True
            logger.warning(f"[rag/retriever] reranker unavailable, using vector scores only: {e}\n")
            return None


def retrieve(query: str, topics: list = None, tags: list = None, progress_callback=None) -> list:
    workspace = config.workspace_path
    if not workspace:
        return []

    from sidecar.rag.embedder import encode_query
    query_emb = encode_query(query)
    if not query_emb.get("dense_vec"):
        return []

    from sidecar.rag.profile import rewrite_query_with_profile
    profile_query = rewrite_query_with_profile(query)

    from sidecar.rag.index import filter_usable_chunks, hybrid_search
    top_k = SEARCH_TOP_K_TAGS if (topics or tags) else DEFAULT_TOP_K
    results = hybrid_search(
        workspace,
        query_dense=query_emb["dense_vec"],
        query_sparse=query_emb.get("lexical_weights", {}),
        top_k=top_k,
        topics=topics,
        tags=tags,
    )

    if not results or (results and results[0].get("score", 0) < HYDE_TRIGGER_BELOW_SCORE):
        hyde_results = _hyde_search(workspace, query, topics, tags, progress_callback)
        if hyde_results:
            existing_ids = {r.get("id") for r in results}
            for r in hyde_results:
                if r.get("id") not in existing_ids:
                    results.append(r)
                    existing_ids.add(r.get("id"))
            results.sort(key=lambda x: x.get("score", 0), reverse=True)
            results = results[:top_k]

    if not results and profile_query != query:
        profile_emb = encode_query(profile_query)
        if profile_emb.get("dense_vec"):
            results = hybrid_search(
                workspace,
                query_dense=profile_emb["dense_vec"],
                query_sparse=profile_emb.get("lexical_weights", {}),
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
    return filter_usable_chunks(expanded)


def _hyde_search(workspace, query, topics, tags, progress_callback=None) -> list:
    try:
        from prompts import HYDE_PROMPT
        from utils.llm_utils import create_llm

        prompt = HYDE_PROMPT.format(query=query)
        llm = create_llm(temperature=0.3)
        result = llm.invoke(prompt)
        hypo_answer = result.content if hasattr(result, "content") else str(result)

        from sidecar.rag.embedder import encode_query
        hyde_emb = encode_query(hypo_answer)
        if not hyde_emb.get("dense_vec"):
            return []

        from sidecar.rag.index import hybrid_search
        return hybrid_search(
            workspace,
            query_dense=hyde_emb["dense_vec"],
            query_sparse=hyde_emb.get("lexical_weights", {}),
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

    from sidecar.rag.embedder import encode
    try:
        contents = [r.get("content", "") for r in results]
        if not any(contents):
            return results[:top_k]

        embeddings = encode(contents)
        dense_vecs = embeddings["dense_vecs"]

        import numpy as np
        norms = np.linalg.norm(dense_vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        norm_vecs = dense_vecs / norms

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
        reranker = _get_reranker()
        if reranker is None:
            return results[:top_k]

        pairs = [[query, r.get("content", "")] for r in results if r.get("content")]
        if not pairs:
            return results[:top_k]

        scores = reranker.compute_score(pairs, normalize=True)

        if isinstance(scores, float):
            scores = [scores]

        for i, score in enumerate(scores):
            if i < len(results):
                results[i]["rerank_score"] = float(score)

        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return results[:top_k]
    except ImportError:
        return results[:top_k]
    except Exception as e:
        logger.warning(f"[rag/retriever] rerank error: {e}\n")
        return results[:top_k]


def rebuild_index(progress_callback=None):
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    from sidecar.rag.chunker import chunk_file
    from sidecar.rag.embedder import encode_documents
    from sidecar.rag.index import build_index

    workspace_path = Path(workspace)
    excluded_dirs = {
        ".git",
        ".obsidian",
        ".trash",
        ".rag_index",
        ".ai_memory",
        "Raw",
        WORKSPACE_APP_FOLDER,
        RAG_INDEX_FOLDER,
    }
    all_chunks = []

    for md_file in sorted(workspace_path.rglob("*.md")):
        if md_file.name.startswith("."):
            continue
        if "wiki" in md_file.parts:
            continue
        if any(p.name in excluded_dirs or is_ignored_dir(p.name) for p in md_file.relative_to(workspace_path).parents):
            continue
        if md_file.name.endswith("_综述.md") or md_file.name.endswith("综述.md"):
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
            chunks = chunk_file(str(md_file), text)
            all_chunks.extend(chunks)
        except Exception as e:
            logger.warning(f"[rag/retriever] chunk error {md_file}: {e}\n")

    if not all_chunks:
        return {"success": False, "message": "未找到可索引的文件"}

    if progress_callback:
        progress_callback(0, len(all_chunks), "正在生成 Embedding...")

    texts = [c["content"] for c in all_chunks]
    try:
        embeddings = encode_documents(texts, download_callback=lambda msg: progress_callback(0, 1, msg) if progress_callback else None)
    except Exception as e:
        return {"success": False, "message": f"Embedding 生成失败: {e}"}

    if progress_callback:
        progress_callback(len(all_chunks) // 2, len(all_chunks), "正在构建索引...")

    result = build_index(workspace, all_chunks, embeddings, progress_callback=progress_callback)

    from sidecar.rag.profile import update_profile_from_topics
    topic_counts = {}
    for c in all_chunks:
        t = c.get("topic", "")
        if t:
            topic_counts[t] = topic_counts.get(t, 0) + 1
    sorted_topics = sorted(topic_counts.keys(), key=lambda x: topic_counts[x], reverse=True)
    update_profile_from_topics(sorted_topics)

    return result


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
