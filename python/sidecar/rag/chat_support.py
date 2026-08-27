"""RAG chat helpers extracted from RagHandler (history, suggestions, citations)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from utils.logger import logger

_SUGGESTIONS_SENTINEL_RE = re.compile(r"SUGGESTIONS_JSON:\s*(\[[^\]]*\])")


def _jieba_analyse_available():
    """Check if jieba.analyse is importable (lazy, cached)."""
    try:
        import jieba.analyse  # noqa: F401

        return True
    except ImportError:
        return False


def _strip_suggestions_sentinel(answer: str) -> tuple[str, list[str]]:
    """Split the trailing SUGGESTIONS_JSON sentinel; return (body, suggestions)."""
    raw = answer or ""
    m = _SUGGESTIONS_SENTINEL_RE.search(raw)
    if not m:
        return raw, []
    body = raw[: m.start()].rstrip()
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, TypeError, ValueError):
        return body, []
    if not isinstance(data, list):
        return body, []
    suggestions = [str(s).strip() for s in data if str(s).strip()][:3]
    return body, suggestions


def _session_topic_anchors(history) -> list[str]:
    """Session-only topic anchoring: extract anchor terms from early turns.

    When the session history exceeds 6 messages, the messages before the
    last 6 are compressed via _extractive_compress and mined for
    high-value terms (jieba TF-IDF) used as extra retrieval keywords.
    Lives only in-session: never persisted, no automatic extraction
    pipeline (PRD §3/§12.6).
    """
    if not isinstance(history, list) or len(history) <= 6:
        return []
    older = [m for m in history[:-6] if isinstance(m, dict)]
    if not older or not _jieba_analyse_available():
        return []
    try:
        text = _extractive_compress(older)
        if not text.strip():
            text = " ".join(str(m.get("content") or "")[:300] for m in older if m.get("role") == "user")
        if not text.strip():
            return []
        import jieba.analyse

        return list(jieba.analyse.extract_tags(text, topK=5, withWeight=False))
    except Exception as e:
        logger.warning(f"[rag] topic anchoring failed: {e}")
        return []


def _template_suggestions(citations: list | None) -> list[str]:
    """Fallback follow-up suggestions built from citation metadata (no LLM)."""
    suggestions: list[str] = []
    seen: set[str] = set()
    for c in citations or []:
        if not isinstance(c, dict):
            continue
        topic = str(c.get("topic") or "").strip()
        section = str(c.get("section_title") or "").strip()
        label = str(c.get("source_label") or c.get("file_name") or "").strip()
        if topic and topic not in seen:
            suggestions.append(f"「{topic}」还有哪些相关笔记？")
            seen.add(topic)
        elif section and section not in seen:
            suggestions.append(f"展开讲讲「{section}」")
            seen.add(section)
        elif label and label not in seen:
            suggestions.append(f"《{label}》里还有什么要点？")
            seen.add(label)
        if len(suggestions) >= 3:
            break
    return suggestions[:3]


def _limited_history(raw_history) -> str:
    if not isinstance(raw_history, list):
        return ""
    lines = []
    for message in raw_history[-6:]:
        if not isinstance(message, dict):
            continue
        role = "用户" if message.get("role") == "user" else "助手"
        content = str(message.get("content") or "").strip()[:1200]
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)[:5000]


def _load_user_profile(workspace: str) -> str:
    profile_path = Path(workspace) / ".ai_memory" / "user_profile.json"
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(data.get("profile_md") or "").strip()[:4000]


def _personal_context(profile: str, history: str) -> str:
    parts = []
    if profile:
        parts.append(f"用户画像（仅用于理解用户背景，不视为知识库证据）：\n{profile}")
    if history:
        parts.append(f"当前会话最近上下文：\n{history}")
    return "\n\n".join(parts)


def _citation_quality(citations: list | None) -> dict:
    cites = citations or []
    scored = []
    for cite in cites:
        try:
            scored.append(float(cite.get("score")))
        except (TypeError, ValueError):
            continue
    source_count = len([c for c in cites if c.get("file_path")])
    top_score = max(scored) if scored else None
    if source_count == 0:
        level = "none"
    elif top_score is None or top_score < 0.22:
        level = "weak"
    elif source_count >= 6:
        level = "broad"
    elif source_count <= 3 and (top_score is None or top_score >= 0.72):
        level = "focused"
    else:
        level = "balanced"
    return {"source_count": source_count, "level": level, "top_score": top_score}


def _build_retrieval_meta(
    intent: str, hyde_enabled_flag: bool, hyde_query: str | None, retrieval_debug: dict | None, search_results: list
) -> dict:
    top_sources = []
    for r in search_results[:5]:
        if not isinstance(r, dict):
            continue
        top_sources.append(
            {
                "path": r.get("file_path") or "",
                "section_title": r.get("section_title") or "",
                "score": r.get("score"),
                "rerank_score": r.get("rerank_score"),
            }
        )
    return {
        "intent": intent,
        "hyde_enabled": bool(hyde_enabled_flag),
        "hyde_query": (str(hyde_query)[:200] if hyde_query else None),
        "retrieval_debug": retrieval_debug or {},
        "top_sources": top_sources,
    }


def _cited_sources(answer: str, citations: list[dict]) -> list[dict]:
    """Return only valid source IDs the model actually used in its answer."""
    by_index = {str(c.get("index")): c for c in citations if c.get("index") is not None}
    used = []
    seen: set[str] = set()
    for match in re.finditer(r"\[(\d+)\]", answer or ""):
        index = match.group(1)
        if index in by_index and index not in seen:
            used.append(by_index[index])
            seen.add(index)
    return used


def _extractive_compress(older_history):
    if not older_history:
        return ""
    if isinstance(older_history, str):
        return older_history[:800]

    parts = []
    for h in older_history:
        if not isinstance(h, dict):
            continue
        role = "用户" if h.get("role") == "user" else "助手"
        text = str(h.get("content") or "")
        if not text:
            continue
        if len(text) <= 80:
            parts.append(f"{role}: {text}")
            continue

        sentences = re.split(r"[。！？\n]", text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 3]

        if not sentences:
            parts.append(f"{role}: {text[:80]}…")
            continue

        if len(sentences) == 1:
            first = sentences[0][:80]
        else:
            first = sentences[0][:60]
            last = sentences[-1][:60] if sentences[-1] != sentences[0] else ""
            if last:
                first = first + "…" + last

        if not _jieba_analyse_available():
            parts.append(f"{role}: {first}…")
            continue

        import jieba.analyse

        keywords = jieba.analyse.extract_tags(text, topK=3, withWeight=False)
        kw_str = "、".join(keywords) if keywords else ""

        if kw_str:
            parts.append(f"{role}: {first}… [关键词: {kw_str}]")
        else:
            parts.append(f"{role}: {first}…")

    return "\n".join(parts)
