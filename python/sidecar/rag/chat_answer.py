"""RAG answer generation (workspace evidence vs web / no-context)."""

from __future__ import annotations

from pathlib import Path

from config import config
from sidecar.rag.chat_stream import RagChatChunkBatcher
from sidecar.rag.question_shape import classify_question_shape
from utils.logger import logger

_SKELETON_SOURCE_TYPES = frozenset({"survey"})
_SKIP_SOURCE_TYPES = frozenset({"backlink", "topic_tree"})


def _shape_instructions(shape: str) -> str:
    from prompts import (
        RAG_CHAT_SHAPE_COMPARE,
        RAG_CHAT_SHAPE_DEFAULT,
        RAG_CHAT_SHAPE_DEFINE,
        RAG_CHAT_SHAPE_GAP,
        RAG_CHAT_SHAPE_TEACH,
    )

    return {
        "define": RAG_CHAT_SHAPE_DEFINE,
        "teach": RAG_CHAT_SHAPE_TEACH,
        "compare": RAG_CHAT_SHAPE_COMPARE,
        "gap": RAG_CHAT_SHAPE_GAP,
    }.get(shape, RAG_CHAT_SHAPE_DEFAULT)


def answer_without_retrieval(handler, question: str, compressed_history: str, *, intent: str = "general") -> dict:
    cls = type(handler)
    from prompts import ASSISTANT_PERSONA_PROMPT, RAG_ASSISTANT_NO_CONTEXT_PROMPT, RAG_ASSISTANT_WEB_PROMPT
    from utils.llm_utils import APIConfigError, call_llm_raw_stream

    memory_section = f"对话历史：{compressed_history}\n\n" if compressed_history else ""

    if intent == "web":
        from sidecar.rag.web_search import search_and_fetch

        web_results = []
        try:
            web_results = search_and_fetch(question, max_pages=2)
        except Exception as e:
            logger.warning(f"[rag/web] search failed: {e}")

        web_context_parts = []
        for idx, r in enumerate(web_results, 1):
            title = r.get("title", "")
            url = r.get("url", "")
            content = (r.get("content") or r.get("snippet") or "").strip()[:1200]
            if title or content:
                web_context_parts.append(f"[{idx}] {title}\n{url}\n{content}")

        web_context = "\n\n".join(web_context_parts) if web_context_parts else "未搜索到有效结果。"
        prompt = RAG_ASSISTANT_WEB_PROMPT.format(
            persona=ASSISTANT_PERSONA_PROMPT,
            memory_section=memory_section,
            web_context=web_context,
            question=question,
        )
    else:
        prompt = RAG_ASSISTANT_NO_CONTEXT_PROMPT.format(
            persona=ASSISTANT_PERSONA_PROMPT,
            memory_section=memory_section,
            question=question,
        )

    try:
        batcher = RagChatChunkBatcher(handler._send_response)
        try:
            answer = call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=batcher.append)
        finally:
            batcher.flush()
    except APIConfigError as e:
        cls._record_error(f"LLM调用失败: {e}")
        return handler._fail_rag(str(e))
    except Exception as e:
        cls._record_error(f"LLM错误: {e}")
        return handler._fail_rag(str(e))

    citations = []
    if intent == "web":
        citations = [
            {
                "index": i,
                "file_path": "",
                "file_name": result.get("title", ""),
                "source_label": result.get("title", ""),
                "source_type": "web",
                "url": result.get("url", ""),
            }
            for i, result in enumerate(web_results, 1)
            if result.get("url")
        ]
    return handler._finish_chat(question, answer, citations=citations)


def answer_with_rag(handler, params, question: str, compressed_history: str, *, intent: str = "workspace") -> dict:
    cls = type(handler)
    from prompts import RAG_CHAT_PROMPT
    from sidecar.rag.retriever import retrieve as vector_retrieve
    from utils.llm_utils import APIConfigError, call_llm_raw_stream

    topics = params.get("topics") or None
    tags = params.get("tags") or None
    current_file = params.get("current_file") or ""

    retrieval_debug: dict | None = None
    hyde_enabled_flag = False
    hyde_query: str | None = None
    try:
        # Session-only topic anchoring: append anchor terms from early
        # turns as extra retrieval keywords (original query kept intact).
        anchors = cls._session_topic_anchors(params.get("history"))
        retrieval_query = f"{question} {' '.join(anchors)}" if anchors else question
        retrieval = vector_retrieve(
            retrieval_query,
            topics=topics,
            tags=tags,
            current_file=current_file,
        )
        search_results = retrieval.get("results") or []
        retrieval_debug = dict(retrieval.get("retrieval_debug") or {})
        if anchors:
            retrieval_debug["anchor_terms"] = anchors
        hyde_enabled_flag = bool(retrieval_debug.get("hyde_enabled"))
        hyde_query = retrieval_debug.get("hyde_query")
    except Exception as e:
        cls._record_error(f"检索失败: {e}")
        return handler._fail_rag(f"检索失败: {e}")

    context_parts: list[str] = []
    citations: list[dict] = []
    seen_paths: set[str] = set()

    # Object-layer injection: extracted entities/concepts (with descriptions)
    # ground the answer in the knowledge base's structured objects.
    # Best-effort — a missing or broken semantic DB yields no object items.
    object_items: list[dict] = []
    try:
        from sidecar.rag.object_context import retrieve_object_context

        object_items = retrieve_object_context(config.workspace_path, question, topics=topics, tags=tags)
    except Exception as e:
        logger.warning(f"[rag/object_context] injection failed: {e}")
    for r in object_items:
        body = (r.get("content") or "").strip()
        if not body:
            continue
        idx = len(context_parts) + 1
        label = r.get("source_label") or "知识库对象"
        context_parts.append(f"[{idx}] {label}\n{body}")
        citations.append(
            {
                "index": idx,
                "file_path": "",
                "file_name": "",
                "source_label": label,
                "section_title": "",
                "topic": r.get("topic") or "",
                "source_type": "object",
                "score": r.get("score", 0),
            }
        )

    skeleton_parts: list[str] = []
    for r in search_results:
        source_type = r.get("source_type")
        # Graph neighbors stay retrieval-only; surveys become a teaching
        # skeleton and must not be numbered as [n] evidence.
        if source_type in _SKIP_SOURCE_TYPES:
            continue
        body = (r.get("content") or "").strip()
        if not body:
            continue
        if source_type in _SKELETON_SOURCE_TYPES:
            label = r.get("source_label") or r.get("file_name") or r.get("file_path") or "主题综述"
            skeleton_parts.append(f"{label}\n{body}")
            continue
        fp = r.get("file_path", "")
        if fp and fp in seen_paths:
            continue
        if fp:
            seen_paths.add(fp)
        label = r.get("source_label") or r.get("file_name") or fp or ""
        idx = len(context_parts) + 1
        context_parts.append(f"[{idx}] {label}\n{body}")
        citations.append(
            {
                "index": idx,
                "file_path": fp,
                "file_name": r.get("file_name") or Path(fp).stem,
                "source_label": r.get("source_label") or "",
                "section_title": r.get("section_title") or "",
                "topic": r.get("topic") or "",
                "source_type": r.get("source_type") or "vector",
                "score": r.get("rerank_score", r.get("score")),
            }
        )
    sections: list[str] = []
    if skeleton_parts:
        sections.append("【讲解骨架】\n" + "\n\n".join(skeleton_parts))
    if context_parts:
        sections.append("【可引用原文】\n" + "\n\n".join(context_parts))
    context = "\n\n".join(sections)

    # P9: emit retrieval transparency meta after retrieval, before the
    # answer stream starts.
    meta_data = handler._build_retrieval_meta(intent, hyde_enabled_flag, hyde_query, retrieval_debug, search_results)
    handler._send_response(
        {
            "id": "event",
            "result": {
                "type": "rag_retrieval",
                "subtype": "meta",
                "session_id": str(params.get("session_id") or ""),
                "data": meta_data,
            },
        }
    )

    if not context.strip():
        # No evidence at all: explicitly declare the knowledge base has no
        # directly relevant material instead of letting the model improvise
        # with an empty context (which encourages fabricated citations).
        from prompts import ASSISTANT_PERSONA_PROMPT, RAG_ASSISTANT_NO_EVIDENCE_PROMPT

        memory_section = f"对话历史：{compressed_history}\n\n" if compressed_history else ""
        prompt = RAG_ASSISTANT_NO_EVIDENCE_PROMPT.format(
            persona=ASSISTANT_PERSONA_PROMPT,
            memory_section=memory_section,
            question=question,
        )
    else:
        prompt = RAG_CHAT_PROMPT.format(
            context=context,
            history=compressed_history if compressed_history else "无历史对话",
            question=question,
            shape_instructions=_shape_instructions(classify_question_shape(question)),
        )

    try:
        batcher = RagChatChunkBatcher(handler._send_response)
        try:
            answer = call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=batcher.append)
        finally:
            batcher.flush()
    except APIConfigError as e:
        cls._record_error(f"LLM调用失败: {e}")
        return handler._fail_rag(str(e))
    except Exception as e:
        cls._record_error(f"LLM错误: {e}")
        return handler._fail_rag(str(e))

    return handler._finish_chat(question, answer, citations=handler._cited_sources(answer, citations))
