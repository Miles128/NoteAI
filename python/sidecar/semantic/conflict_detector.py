"""结构化命题冲突检测（设计雏形）。

目标：把知识库内相互矛盾的结论用确定性规则找出，写入 review_queue
（item_kind='claim_conflict'），供语义工作台「冲突」页审阅。纯规则、
不引入 LLM 判定，保证结果可解释、可复现。

规则（仅对 active conclusion 之间判定）：
- A comparison（比较对立）：同一对象对的比较方向相反。
  「X 优于 Y」↔「Y 优于 X」；「X 优于 Y」↔「X 劣于 Y」。
- B change/attribute（变化与属性对立）：同一主体对同一目标（可为空）
  的极性动词相反。「X 提升 Y」↔「X 降低 Y」；「X 有效」↔「X 无效」。

适用范围限定：两个命题同 topic，或 scope 非空且相同，才判冲突；
hypothesis 不参与（待验证推测与结论不构成既定矛盾）。

已知局限（雏形刻意不做）：
- 不做语义蕴含/同义对象归并，只做文本归一化比较（同义归并可复用
  实体合并后的规范名，属后续迭代）。
- 「X 优于 Y」与「X 比 Y 快」这类表达不归一，可能漏检。
- 语气词等噪声可能混入 target，导致个别本应冲突的对漏检。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sidecar.semantic.ids import normalize_text, stable_id
from sidecar.semantic.store import SemanticStore

# 方向以「前项」为准：前项 优于/提升/有效 后项 => +1
_COMPARE_VERBS = "优于|胜过|强于|高于|快于|好于|大于|多于|胜于|劣于|不如|弱于|低于|慢于|差于|小于|少于|落后于"
_CHANGE_VERBS = "提升|提高|改善|增强|增长|上升|增加|促进|有助于|加快|加速|降低|下降|减少|削弱|恶化|抑制|减慢|拖累"
_ATTRIBUTE_VERBS = (
    "有效|可靠|稳健|适合|有益|合理|可行|重要|关键|优秀|出色|无效|不可靠|不适合|有害|不合理|不可行|不足|较差"
)

_VERB_RE = re.compile(
    rf"(?P<subject>[^，。；、\s,;]{{2,24}}?)(?P<rel>{_COMPARE_VERBS}|{_CHANGE_VERBS}|{_ATTRIBUTE_VERBS})(?P<target>[^，。；、\s,;]{{0,24}})"
)
_COMPARE_VERB_SET = set(_COMPARE_VERBS.split("|"))
_CHANGE_VERB_SET = set(_CHANGE_VERBS.split("|"))
_POS = (
    {"优于", "胜过", "强于", "高于", "快于", "好于", "大于", "多于", "胜于"}
    | {"提升", "提高", "改善", "增强", "增长", "上升", "增加", "促进", "有助于", "加快", "加速"}
    | {"有效", "可靠", "稳健", "适合", "有益", "合理", "可行", "重要", "关键", "优秀", "出色"}
)
_NEG = (
    {"劣于", "不如", "弱于", "低于", "慢于", "差于", "小于", "少于", "落后于"}
    | {"降低", "下降", "减少", "削弱", "恶化", "抑制", "减慢", "拖累"}
    | {"无效", "不可靠", "不适合", "有害", "不合理", "不可行", "不足", "较差"}
)

_ITEM_KIND = "claim_conflict"
_MAX_CANDIDATES_PER_GROUP = 20


@dataclass(frozen=True)
class Polarity:
    """One extracted polarity assertion from a claim statement."""

    kind: str  # 'comparison' | 'change' | 'attribute'
    subject: str  # normalized
    target: str  # normalized, may be empty
    direction: int  # +1 / -1
    rel: str


def extract_polarities(statement: str) -> list[Polarity]:
    """Extract polarity assertions from a normalized statement.

    Comparison verbs (优于/劣于 …) always form a (subject, target) pair and
    their direction is remapped onto the lexicographically first member so
    that「X 优于 Y」and「Y 劣于 X」collapse onto the same conflict key.
    """
    text = normalize_text(statement)
    found: list[Polarity] = []
    for match in _VERB_RE.finditer(text):
        subject = normalize_text(match.group("subject"))
        rel = match.group("rel")
        target = normalize_text(match.group("target"))
        if not subject:
            continue
        direction = 1 if rel in _POS else -1
        if rel in _COMPARE_VERB_SET and subject > target:
            direction = -direction
            subject, target = target, subject
        kind = "comparison" if rel in _COMPARE_VERB_SET else ("change" if rel in _CHANGE_VERB_SET else "attribute")
        found.append(Polarity(kind=kind, subject=subject, target=target, direction=direction, rel=rel))
    return found


def _claims_snapshot(store: SemanticStore) -> list[dict]:
    """Active conclusions with their document topic and scope."""
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT DISTINCT c.id, c.statement, c.scope, c.claim_type,
                      COALESCE(d.topic, '') AS topic
               FROM claims c
               LEFT JOIN evidence e ON e.claim_id = c.id AND e.status = 'active'
               LEFT JOIN blocks b ON b.id = e.block_id
               LEFT JOIN documents d ON d.id = b.document_id
               WHERE c.status = 'active' AND c.claim_type = 'conclusion'
               ORDER BY c.id"""
        ).fetchall()
    return [dict(row) for row in rows]


def _same_context(left: dict, right: dict) -> bool:
    left_scope = normalize_text(left["scope"])
    right_scope = normalize_text(right["scope"])
    if left["topic"] and right["topic"] and left["topic"] == right["topic"]:
        return True
    return bool(left_scope and left_scope == right_scope)


def detect_claim_conflicts(store: SemanticStore) -> list[dict]:
    """Deterministically derive conflict candidates from the current snapshot.

    Returns candidate dicts (not persisted):
    {id, claim_a_id, claim_b_id, claim_a, claim_b, rule, reason,
     direction_a, direction_b, polarity_a, polarity_b, fingerprint}
    """
    claims = _claims_snapshot(store)
    by_id = {claim["id"]: claim for claim in claims}
    groups: dict[tuple[str, str, str], list[tuple[dict, Polarity]]] = {}
    for claim in claims:
        for polarity in extract_polarities(claim["statement"]):
            key = (polarity.kind, polarity.subject, polarity.target)
            groups.setdefault(key, []).append((claim, polarity))

    candidates: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for (kind, _subject, _target), members in groups.items():
        positives = [item for item in members if item[1].direction > 0]
        negatives = [item for item in members if item[1].direction < 0]
        if not positives or not negatives:
            continue
        for left_claim, left_polarity in positives[: _MAX_CANDIDATES_PER_GROUP // 2]:
            for right_claim, right_polarity in negatives[: _MAX_CANDIDATES_PER_GROUP // 2]:
                if left_claim["id"] == right_claim["id"]:
                    continue
                if not _same_context(left_claim, right_claim):
                    continue
                pair = tuple(sorted((left_claim["id"], right_claim["id"])))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                claim_a = left_claim
                claim_b = right_claim
                direction_a = left_polarity.direction
                direction_b = right_polarity.direction
                if claim_a["id"] != pair[0]:
                    claim_a, claim_b = claim_b, claim_a
                    direction_a, direction_b = direction_b, direction_a
                rule = "comparison" if kind == "comparison" else "polarity"
                fingerprint = stable_id(
                    "cfp",
                    claim_a["id"],
                    claim_b["id"],
                    rule,
                    kind,
                    left_polarity.subject,
                    left_polarity.target,
                )
                candidates.append(
                    {
                        "id": stable_id("cfl", claim_a["id"], claim_b["id"]),
                        "claim_a_id": claim_a["id"],
                        "claim_b_id": claim_b["id"],
                        "claim_a": claim_a["statement"],
                        "claim_b": claim_b["statement"],
                        "rule": rule,
                        "kind": kind,
                        "reason": _build_reason(kind, left_polarity, right_polarity),
                        "direction_a": direction_a,
                        "direction_b": direction_b,
                        "polarity_a": left_polarity.rel,
                        "polarity_b": right_polarity.rel,
                        "fingerprint": fingerprint,
                    }
                )
    return candidates


def _build_reason(kind: str, left: Polarity, right: Polarity) -> str:
    subject = left.subject or right.subject
    target = left.target or right.target
    if kind == "comparison":
        return f"同一对象对「{subject} ↔ {target}」的比较结论方向相反：一个说「{left.rel}」，另一个说「{right.rel}」"
    if target:
        return f"对「{subject} {target}」的结论方向相反：一个说「{left.rel}」，另一个说「{right.rel}」"
    return f"对「{subject}」的结论方向相反：一个说「{left.rel}」，另一个说「{right.rel}」"


def persist_claim_conflicts(store: SemanticStore, candidates: list[dict]) -> dict:
    """Upsert conflict candidates into review_queue (idempotent).

    - A candidate whose fingerprint matches an already-reviewed row keeps its
      reviewed status; otherwise it is reset to pending.
    - Pending items whose claims no longer exist (deleted/removed) are purged.
    """
    with store.connect() as conn:
        active_ids = {candidate["claim_a_id"] for candidate in candidates} | {
            candidate["claim_b_id"] for candidate in candidates
        }
        stale = conn.execute("SELECT id, payload_json FROM review_queue WHERE item_kind = ?", (_ITEM_KIND,)).fetchall()
        for row in stale:
            payload = json.loads(row["payload_json"] or "{}")
            if payload.get("claim_a_id") not in active_ids or payload.get("claim_b_id") not in active_ids:
                conn.execute("DELETE FROM review_queue WHERE id = ?", (row["id"],))
        now = store._now()
        for candidate in candidates:
            payload = {
                "claim_a_id": candidate["claim_a_id"],
                "claim_b_id": candidate["claim_b_id"],
                "claim_a": candidate["claim_a"],
                "claim_b": candidate["claim_b"],
                "rule": candidate["rule"],
                "kind": candidate["kind"],
                "direction_a": candidate["direction_a"],
                "direction_b": candidate["direction_b"],
                "polarity_a": candidate["polarity_a"],
                "polarity_b": candidate["polarity_b"],
                "fingerprint": candidate["fingerprint"],
            }
            existing = conn.execute(
                "SELECT status, payload_json FROM review_queue WHERE id = ?", (candidate["id"],)
            ).fetchone()
            status = "reviewed" if existing and existing["status"] == "reviewed" else "pending"
            if existing and existing["status"] == "reviewed":
                old_fingerprint = json.loads(existing["payload_json"] or "{}").get("fingerprint")
                if old_fingerprint != candidate["fingerprint"]:
                    status = "pending"
            conn.execute(
                """INSERT INTO review_queue(id, item_kind, payload_json, reason, status, created_at)
                   VALUES(?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json,
                                                reason = excluded.reason, status = excluded.status,
                                                created_at = excluded.created_at""",
                (
                    candidate["id"],
                    _ITEM_KIND,
                    json.dumps(payload, ensure_ascii=False),
                    candidate["reason"],
                    status,
                    now,
                ),
            )
            SemanticStore._audit(
                conn,
                action="scan_conflict" if status == "pending" else "rescan_conflict",
                object_kind="claim_conflict",
                object_id=candidate["id"],
                before={},
                after={
                    "rule": candidate["rule"],
                    "claim_a": candidate["claim_a_id"],
                    "claim_b": candidate["claim_b_id"],
                    "status": status,
                    "fingerprint": candidate["fingerprint"],
                },
            )
    return {"success": True, "candidates": len(candidates)}


def scan_and_persist(store: SemanticStore) -> dict:
    """Full pipeline: derive candidates from the snapshot and persist them."""
    candidates = detect_claim_conflicts(store)
    return persist_claim_conflicts(store, candidates)
