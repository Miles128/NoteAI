"""Retrieval result shaping policy: dynamic citation count and source limits."""

from __future__ import annotations


def query_complexity(query: str) -> str:
    q = (query or "").strip()
    lower = q.lower()
    broad_terms = (
        "比较",
        "区别",
        "对比",
        "总结",
        "综述",
        "有哪些",
        "如何",
        "为什么",
        "方案",
        "路线",
        "步骤",
        "优缺点",
        "compare",
        "difference",
        "summarize",
        "overview",
        "strategy",
        "plan",
        "roadmap",
        "pros and cons",
        "why",
        "how",
    )
    broad_hits = sum(1 for term in broad_terms if term in lower)
    separators = sum(q.count(ch) for ch in "，,；;、/和与")
    if len(q) <= 24 and broad_hits == 0 and separators <= 1:
        return "easy"
    if broad_hits >= 2 or len(q) >= 80 or separators >= 4:
        return "broad"
    return "medium"


def result_score(row: dict) -> float:
    for key in ("rerank_score", "score", "dense_score", "sparse_score"):
        if key not in row or row.get(key) is None:
            continue
        try:
            return float(row.get(key))
        except (TypeError, ValueError):
            continue
    return 0.0


def unique_count(results: list, key: str) -> int:
    return len({str(r.get(key) or "").strip() for r in results if str(r.get(key) or "").strip()})


def select_dynamic_top_k(query: str, results: list) -> int:
    """Choose how many retrieved chunks to cite based on query breadth and score shape."""
    if not results:
        return 0
    usable = [r for r in results if (r.get("content") or "").strip()]
    if not usable:
        return 0
    scores = [result_score(r) for r in usable]
    top = scores[0] if scores else 0.0
    second = scores[1] if len(scores) > 1 else 0.0
    gap = top - second
    complexity = query_complexity(query)

    if top < 0.22:
        return min(2, len(usable))

    if complexity == "easy":
        k = 2 if top >= 0.72 and gap >= 0.18 else 3
    elif complexity == "broad":
        k = 6
        if unique_count(usable[:10], "file_path") >= 6 or unique_count(usable[:10], "topic") >= 4:
            k = 8
    else:
        k = 4
        if len(scores) >= 5 and scores[4] >= max(0.38, top * 0.62):
            k = 5

    return min(max(k, 1), 8, len(usable))


def limit_unique_sources(results: list, max_sources: int) -> list:
    if max_sources <= 0:
        return []
    out = []
    seen: set[str] = set()
    for row in results:
        source = str(row.get("file_path") or row.get("id") or "").strip()
        if source and source not in seen and len(seen) >= max_sources:
            continue
        if source:
            seen.add(source)
        out.append(row)
    return out
