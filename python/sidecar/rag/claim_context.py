"""Claim-layer retrieval for RAG chat: verified conclusions + conflict alerts.

P0 消费侧接入：让 RAG 问答能引用知识库内已提炼的命题（claims），并把
联网核查结论（claim_verifications）与结构化冲突候选（review_queue 的
claim_conflict）一并注入上下文，回答时不会忽略知识库内部矛盾。

检索是确定性的（jieba 分词 + 词重叠打分），不依赖 embedding 或额外
LLM 调用；semantic.db 不存在或为空时静默返回空列表，不影响原有链路。
"""

from __future__ import annotations

import json
from pathlib import Path

from sidecar.semantic.claim_verifier import verdict_label
from sidecar.semantic.store import SemanticStore

try:
    import jieba  # type: ignore[import-untyped]

    _HAS_JIEBA = True
except ImportError:  # pragma: no cover - jieba is a project dependency
    _HAS_JIEBA = False

_MAX_CLAIMS = 3
_MIN_OVERLAP_RATIO = 0.22
_MIN_COMMON_TOKENS = 2
_MAX_STATEMENT_CHARS = 200
_MAX_SUMMARY_CHARS = 120
_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "吗",
        "呢",
        "啊",
        "吧",
        "是",
        "在",
        "与",
        "和",
        "或",
        "也",
        "都",
        "更",
        "最",
        "比",
        "对",
        "用",
        "中",
        "下",
        "上",
        "里",
        "如何",
        "怎么",
        "怎样",
        "什么",
        "为什么",
        "为何",
        "是否",
        "哪些",
        "哪个",
        "谁",
        "何时",
        "哪里",
        "请",
        "帮我",
        "我",
        "你",
        "他",
        "她",
        "它",
        "这",
        "那",
        "有",
        "没有",
        "不",
        "很",
        "比较",
        "一下",
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "for",
        "and",
        "or",
        "is",
        "are",
    }
)


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    if _HAS_JIEBA:
        raw = {token.strip().casefold() for token in jieba.cut_for_search(text)}
    else:  # pragma: no cover - fallback without jieba
        raw = {char for char in text if not char.isspace()}
    return {token for token in raw if len(token) >= 2 and token not in _STOPWORDS}


def _overlap_score(query_tokens: set[str], statement_tokens: set[str]) -> float:
    if not query_tokens or not statement_tokens:
        return 0.0
    common = query_tokens & statement_tokens
    return len(common) / len(query_tokens)


def _claim_rows(store: SemanticStore, topics: list | None) -> list[dict]:
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT DISTINCT c.id, c.statement, c.scope, c.claim_type,
                      COALESCE(d.topic, '') AS topic,
                      d.path AS evidence_path
               FROM claims c
               JOIN evidence e ON e.claim_id = c.id AND e.status = 'active'
               JOIN blocks b ON b.id = e.block_id
               JOIN documents d ON d.id = b.document_id
               WHERE c.status = 'active'
               ORDER BY c.id"""
        ).fetchall()
    claims: dict[str, dict] = {}
    for row in rows:
        item = claims.setdefault(
            row["id"],
            {
                "id": row["id"],
                "statement": row["statement"],
                "scope": row["scope"] or "",
                "claim_type": row["claim_type"],
                "topic": row["topic"] or "",
                "sources": [],
            },
        )
        if row["evidence_path"] and row["evidence_path"] not in item["sources"]:
            item["sources"].append(row["evidence_path"])
    filtered = [item for item in claims.values() if item["statement"]]
    if topics:
        topic_set = {str(topic).strip().casefold() for topic in topics if topic}
        if topic_set:
            filtered = [
                item for item in filtered if item["topic"].casefold() in topic_set or item["scope"] in topic_set
            ]
    return filtered


def _conflict_map(store: SemanticStore) -> dict[str, list[str]]:
    """claim_id -> opposite statements from active conflict candidates."""
    opposite: dict[str, list[str]] = {}
    with store.connect() as conn:
        rows = conn.execute("SELECT payload_json FROM review_queue WHERE item_kind = 'claim_conflict'").fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        claim_a = payload.get("claim_a_id")
        claim_b = payload.get("claim_b_id")
        statement_a = payload.get("claim_a") or ""
        statement_b = payload.get("claim_b") or ""
        if claim_a and statement_b:
            opposite.setdefault(claim_a, []).append(statement_b)
        if claim_b and statement_a:
            opposite.setdefault(claim_b, []).append(statement_a)
    return opposite


def _claim_entry(
    store: SemanticStore,
    claim: dict,
    verification: dict | None,
    conflicting: list[str],
    score: float,
) -> dict:
    statement = claim["statement"]
    if len(statement) > _MAX_STATEMENT_CHARS:
        statement = statement[:_MAX_STATEMENT_CHARS] + "…"
    parts = [statement]
    if claim["scope"]:
        parts.append(f"（适用范围：{claim['scope']}）")
    if verification:
        summary = (verification.get("summary") or "").strip()
        if len(summary) > _MAX_SUMMARY_CHARS:
            summary = summary[:_MAX_SUMMARY_CHARS] + "…"
        parts.append(
            f"[核查：{verdict_label(verification['verdict'])} {round(float(verification.get('confidence') or 0) * 100)}%"
            + (f"，{summary}" if summary else "")
            + "]"
        )
    else:
        parts.append("[核查：尚未联网核查]")
    for opposite in conflicting:
        parts.append(f"[注意：知识库内存在相反结论：{opposite}]")
    content = "\n".join(parts)

    verdict = verification["verdict"] if verification else "unverified"
    label = "知识库结论·未核查" if verdict == "unverified" else f"知识库结论·{verdict_label(verdict)}"
    if conflicting:
        label += "·存在矛盾"
    evidence_path = (claim["sources"] or [""])[0]
    return {
        "id": f"claim::{claim['id']}",
        "content": content,
        "file_path": evidence_path,
        "file_name": Path(evidence_path).name if evidence_path else "",
        "topic": claim["topic"],
        "source_type": "claim",
        "source_label": label,
        "score": round(score, 4),
        "claim_id": claim["id"],
    }


def retrieve_claim_context(
    workspace: str | Path,
    question: str,
    topics: list | None = None,
    tags: list | None = None,
    limit: int = _MAX_CLAIMS,
) -> list[dict]:
    """Return top claim entries relevant to the question (deterministic).

    Each entry carries the claim statement, its latest verification verdict
    (supported/refuted/unclear) and any directly conflicting claims, so the
    RAG prompt can cite and disclose knowledge-base contradictions.
    """
    del tags  # claims have no tag dimension yet; document-level filtering is a follow-up
    if not workspace or not question:
        return []
    store = SemanticStore(workspace)
    if not store.path.exists():
        return []
    try:
        claims = _claim_rows(store, list(topics or []))
        if not claims:
            return []
        query_tokens = _tokens(question)
        if not query_tokens:
            return []
        # 单条聚合查询取所有 claim 的最新验证（原实现逐 claim 开连接，N+1）
        verification_by_id = store.claims.latest_verifications_for_claims([claim["id"] for claim in claims])
        conflict_by_id = _conflict_map(store)
        scored: list[tuple[float, dict]] = []
        for claim in claims:
            statement_tokens = _tokens(claim["statement"]) | _tokens(claim["scope"])
            ratio = _overlap_score(query_tokens, statement_tokens)
            common = len(query_tokens & statement_tokens)
            if ratio < _MIN_OVERLAP_RATIO and common < _MIN_COMMON_TOKENS:
                continue
            scored.append(
                (
                    ratio,
                    _claim_entry(
                        store,
                        claim,
                        verification_by_id.get(claim["id"]),
                        conflict_by_id.get(claim["id"], [])[:2],
                        ratio,
                    ),
                )
            )
        scored.sort(key=lambda item: (-item[0], item[1]["claim_id"]))
        return [entry for _score, entry in scored[: max(1, min(int(limit), _MAX_CLAIMS))]]
    except Exception:
        # Claim injection is best-effort; a broken semantic DB must never
        # break the conversation path.
        return []
