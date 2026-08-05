"""RAG 对象层注入：把知识库内已提炼的实体/概念（含描述）注入问答上下文。

检索是确定性的（名称子串匹配 + jieba 词重叠打分），不依赖 embedding 或
额外 LLM 调用；semantic.db 不存在或为空时静默返回空列表，不影响原有链路。

低频对象（mention < 2 且 confidence < 0.6）视为偶发提及，默认不注入，
与语义工作台的降级策略（semantic_handler._LOW_FREQ_DEGRADE）保持一致。
"""

from __future__ import annotations

from pathlib import Path

from sidecar.rag.claim_context import _overlap_score, _tokens
from sidecar.semantic.store import SemanticStore

_MAX_OBJECTS = 4
_MIN_OVERLAP_RATIO = 0.25
_MIN_COMMON_TOKENS = 2
_MAX_DESC_CHARS = 120
# 与 semantic_handler._LOW_FREQ_DEGRADE 保持一致的降级门槛。
_DEGRADE_MIN_MENTIONS = 2
_DEGRADE_MIN_CONFIDENCE = 0.6


def _object_rows(store: SemanticStore, topics: list | None) -> list[dict]:
    """Active 实体/概念，附带 mention 计数与来源文档主题列表。"""
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT 'concept' AS kind, id, canonical_name, description,
                      COALESCE(confidence, 0.0) AS confidence, '' AS entity_type,
                      (SELECT count(*) FROM semantic_mentions m
                       WHERE m.object_id = o.id AND m.object_kind = 'concept') AS mention_count
               FROM concepts o
               WHERE o.status = 'active'
               UNION ALL
               SELECT 'entity' AS kind, id, canonical_name, description,
                      COALESCE(confidence, 0.0) AS confidence, entity_type,
                      (SELECT count(*) FROM semantic_mentions m
                       WHERE m.object_id = o.id AND m.object_kind = 'entity') AS mention_count
               FROM entities o
               WHERE o.status = 'active'
               ORDER BY kind, id"""
        ).fetchall()
    objs = [dict(row) for row in rows]
    if not objs:
        return []
    # 一次查询取全部对象 → 来源文档主题映射，供 topic 过滤。
    topic_map: dict[tuple[str, str], list[str]] = {}
    with store.connect() as conn:
        topic_rows = conn.execute(
            """SELECT DISTINCT m.object_id, m.object_kind, d.topic
               FROM semantic_mentions m
               JOIN blocks b ON b.id = m.block_id
               JOIN documents d ON d.id = b.document_id
               WHERE d.topic IS NOT NULL AND d.topic != ''"""
        ).fetchall()
    for row in topic_rows:
        topic_map.setdefault((row["object_id"], row["object_kind"]), []).append(row["topic"] or "")
    for obj in objs:
        obj["topics"] = topic_map.get((obj["id"], obj["kind"]), [])
    if topics:
        topic_set = {str(topic).strip().casefold() for topic in topics if topic}
        if topic_set:
            objs = [
                obj
                for obj in objs
                if any(str(t).casefold() in topic_set for t in obj["topics"])
            ]
    return objs


def _score_object(question: str, obj: dict) -> float:
    """0.0 表示不相关；名称子串命中是最强信号（1.0）。"""
    name = (obj.get("canonical_name") or "").strip()
    if not name:
        return 0.0
    if name.casefold() in question.casefold():
        return 1.0
    query_tokens = _tokens(question)
    if not query_tokens:
        return 0.0
    name_tokens = _tokens(name)
    desc_tokens = _tokens(obj.get("description") or "")
    corpus = name_tokens | desc_tokens
    ratio = _overlap_score(query_tokens, corpus)
    common = len(query_tokens & corpus)
    if ratio < _MIN_OVERLAP_RATIO and common < _MIN_COMMON_TOKENS:
        return 0.0
    # 名称命中权重高于描述命中。
    name_ratio = _overlap_score(query_tokens, name_tokens)
    return ratio * 0.5 + name_ratio * 0.5


def _object_entry(obj: dict, score: float) -> dict:
    name = obj["canonical_name"] or ""
    desc = (obj.get("description") or "").strip()
    if len(desc) > _MAX_DESC_CHARS:
        desc = desc[:_MAX_DESC_CHARS] + "…"
    kind = obj["kind"]
    label = "知识库对象·概念" if kind == "concept" else f"知识库对象·实体（{obj.get('entity_type') or '未分类'}）"
    content = f"{name}：{desc}" if desc else name
    return {
        "id": f"{kind}::{obj['id']}",
        "content": content,
        "file_path": "",
        "file_name": "",
        "topic": (obj.get("topics") or [""])[0],
        "source_type": "object",
        "source_label": label,
        "score": round(score, 4),
        "object_id": obj["id"],
        "object_kind": kind,
    }


def retrieve_object_context(
    workspace: str | Path,
    question: str,
    topics: list | None = None,
    tags: list | None = None,
    limit: int = _MAX_OBJECTS,
) -> list[dict]:
    """Return top entity/concept entries relevant to the question (deterministic).

    Each entry carries the object's canonical name and its extracted
    description, so the RAG prompt can ground answers in the knowledge base's
    structured objects. Best-effort: a missing/broken semantic DB yields [].
    """
    del tags  # objects have no tag dimension yet
    if not workspace or not question:
        return []
    store = SemanticStore(workspace)
    if not store.path.exists():
        return []
    try:
        objs = _object_rows(store, list(topics or []))
        if not objs:
            return []
        query_lower = question.casefold()
        scored: list[tuple[float, dict]] = []
        for obj in objs:
            # 低频降级过滤：偶发提及（mention 少且置信度低）不注入。
            if obj["mention_count"] < _DEGRADE_MIN_MENTIONS and obj["confidence"] < _DEGRADE_MIN_CONFIDENCE:
                continue
            # 名称不在问题中且问题与名称/描述无重叠 → 跳过。
            score = _score_object(query_lower, obj)
            if score <= 0.0:
                continue
            scored.append((score, _object_entry(obj, score)))
        scored.sort(key=lambda item: (-item[0], item[1]["object_kind"], item[1]["object_id"]))
        return [entry for _score, entry in scored[: max(1, min(int(limit), _MAX_OBJECTS))]]
    except Exception:
        # Object injection is best-effort; a broken semantic DB must never
        # break the conversation path.
        return []
