""" lightweight intent router for the assistant. """

from __future__ import annotations

import json
import re
from typing import Any

from utils.logger import logger

_INTENT_ORDER = ("chat", "general", "workspace", "web", "unknown")


def _parse_intent_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
    return None


def classify_intent(question: str, history: str = "") -> dict[str, Any]:
    """Classify the user question into an intent category.

    Returns a dict with keys: intent, confidence, reason.
    If classification fails, falls back to workspace.
    """
    from prompts import INTENT_ROUTER_PROMPT
    from utils.llm_utils import APIConfigError, call_llm_raw, check_api_config

    question = (question or "").strip()
    if not question:
        return {"intent": "unknown", "confidence": "high", "reason": "empty question"}

    # Fast heuristic shortcuts to avoid an LLM call for obvious cases.
    lowered = question.lower()
    if any(
        question.startswith(p)
        for p in ("你好", "您好", "哈喽", "嗨", "hello", "hi", "在吗", "谢谢", "辛苦了", "再见", "拜拜")
    ) or lowered in {"你好", "您好", "哈喽", "嗨", "hello", "hi", "谢谢", "辛苦了"}:
        return {"intent": "chat", "confidence": "high", "reason": "greeting/thanks heuristic"}

    # Keyword-based fallback rules for local-note-related queries.
    workspace_indicators = (
        "我的笔记", "工作区", "笔记里", "笔记中", "我记的", "我记录",
        "主题", "标签", "某篇文章", "某个文件", "这篇文件", "这篇文章",
        "notes/", "wiki/", "guide.md",
    )
    if any(ind in lowered for ind in workspace_indicators):
        return {"intent": "workspace", "confidence": "high", "reason": "workspace keyword detected"}

    web_indicators = (
        "上网查", "搜索网络", "搜一下", "最新新闻", "今天天气", "股价", "行情",
        "twitter", "x.com", "微博", "知乎",
    )
    if any(ind in lowered for ind in web_indicators):
        return {"intent": "web", "confidence": "medium", "reason": "web keyword detected"}

    try:
        ok, _ = check_api_config()
        if not ok:
            raise APIConfigError("API not configured")
    except APIConfigError:
        return {"intent": "workspace", "confidence": "low", "reason": "API unavailable, default to workspace"}

    prompt = INTENT_ROUTER_PROMPT.format(question=question)
    try:
        raw = call_llm_raw(prompt, temperature=0.1, max_tokens=120)
    except Exception as e:
        logger.warning(f"[intent_router] classification failed: {e}")
        return {"intent": "workspace", "confidence": "low", "reason": "classification error, default to workspace"}

    parsed = _parse_intent_json(raw)
    if not parsed:
        return {"intent": "workspace", "confidence": "low", "reason": "unparseable model output, default to workspace"}

    intent = str(parsed.get("intent") or "unknown").lower().strip()
    if intent not in _INTENT_ORDER:
        intent = "unknown"

    return {
        "intent": intent,
        "confidence": str(parsed.get("confidence") or "medium").lower().strip(),
        "reason": str(parsed.get("reason") or "").strip() or "classified by model",
    }
