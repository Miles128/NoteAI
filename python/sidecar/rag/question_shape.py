"""Heuristic question shapes for learning-first RAG answers.

No extra LLM call: classify from surface markers, then pick a prompt block.
"""

from __future__ import annotations

SHAPE_DEFINE = "define"
SHAPE_TEACH = "teach"
SHAPE_COMPARE = "compare"
SHAPE_GAP = "gap"
SHAPE_DEFAULT = "default"

SHAPES = (SHAPE_DEFINE, SHAPE_TEACH, SHAPE_COMPARE, SHAPE_GAP, SHAPE_DEFAULT)

_COMPARE_MARKERS = (
    "对比",
    "区别",
    "差异",
    "不同",
    "相比",
    "versus",
    " vs ",
    "vs.",
    "compare",
    "difference",
    "differ",
)
_GAP_MARKERS = (
    "缺什么",
    "还缺",
    "缺少",
    "盲区",
    "空白",
    "不知道哪些",
    "下一步读",
    "接下来读",
    "该读哪",
    "还要看",
    "what's missing",
    "what am i missing",
    "gap",
    "next notes",
)
_DEFINE_MARKERS = (
    "什么是",
    "是什么",
    "定义",
    "含义",
    "指什么",
    "何为",
    "what is",
    "what's",
    "define",
    "definition",
    "meaning of",
)
_TEACH_MARKERS = (
    "怎么学",
    "如何学",
    "如何理解",
    "怎么理解",
    "讲解",
    "教我",
    "入门",
    "讲清楚",
    "帮我搞懂",
    "通俗",
    "为什么",
    "explain",
    "teach me",
    "how to learn",
    "walk me through",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def classify_question_shape(question: str) -> str:
    """Return define | teach | compare | gap | default.

    Compare and gap win over define/teach so "A 和 B 的区别是什么" stays compare.
    """
    raw = (question or "").strip()
    if not raw:
        return SHAPE_DEFAULT
    text = f" {raw.lower()} "
    if _contains_any(text, _COMPARE_MARKERS) or _contains_any(raw, _COMPARE_MARKERS):
        return SHAPE_COMPARE
    if _contains_any(text, _GAP_MARKERS) or _contains_any(raw, _GAP_MARKERS):
        return SHAPE_GAP
    if _contains_any(text, _DEFINE_MARKERS) or _contains_any(raw, _DEFINE_MARKERS):
        return SHAPE_DEFINE
    if _contains_any(text, _TEACH_MARKERS) or _contains_any(raw, _TEACH_MARKERS):
        return SHAPE_TEACH
    return SHAPE_DEFAULT


def prompt_key_for_shape(shape: str) -> str:
    mapping = {
        SHAPE_DEFINE: "RAG_CHAT_SHAPE_DEFINE",
        SHAPE_TEACH: "RAG_CHAT_SHAPE_TEACH",
        SHAPE_COMPARE: "RAG_CHAT_SHAPE_COMPARE",
        SHAPE_GAP: "RAG_CHAT_SHAPE_GAP",
    }
    return mapping.get(shape, "RAG_CHAT_SHAPE_DEFAULT")
