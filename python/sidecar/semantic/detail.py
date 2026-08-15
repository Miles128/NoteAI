"""Object detail and workbench list assembly for the semantic workbench (read-only)."""

from __future__ import annotations

import json

from sidecar.semantic.store import SemanticStore

# 低频对象降级策略：mention 低于 min_mentions 且置信度低于 min_confidence 的
# 对象视为偶发提及（代表性弱），在非 deep 强度下默认隐藏；主动搜索仍可命中。
LOW_FREQ_DEGRADE = {"min_mentions": 2, "min_confidence": 0.6}


def evidence_row(row) -> dict:
    """Normalize one evidence/mention join row for RPC display."""
    item = dict(row)
    try:
        item["heading_path"] = json.loads(item.pop("heading_path_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        item["heading_path"] = []
    item["excerpt"] = " ".join((item.pop("content", "") or "").split())[:220]
    return item


def build_object_detail(store: SemanticStore, kind: str, object_id: str) -> dict:
    """Assemble one claim/entity/concept detail payload with sources, related
    objects, verifications and audit history. Returns the RPC-ready dict.
    """
    with store.connect() as conn:
        if kind == "claim":
            row = conn.execute(
                "SELECT id, statement, scope, claim_type, confidence, status FROM claims WHERE id = ?",
                (object_id,),
            ).fetchone()
            if row is None:
                return {"success": False, "message": "命题不存在"}
            item = dict(row)
            rows = conn.execute(
                """SELECT e.id, e.status, d.path, d.title, d.topic, b.id AS block_id,
                          b.heading_path_json, b.content, b.start_line, b.end_line
                   FROM evidence e JOIN blocks b ON b.id = e.block_id
                   JOIN documents d ON d.id = b.document_id
                   WHERE e.claim_id = ? ORDER BY d.path, b.ordinal""",
                (object_id,),
            ).fetchall()
        else:
            table = "concepts" if kind == "concept" else "entities"
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (object_id,)).fetchone()
            if row is None:
                return {"success": False, "message": "语义对象不存在"}
            item = dict(row)
            rows = conn.execute(
                """SELECT d.path, d.title, d.topic, b.id AS block_id,
                          b.heading_path_json, b.content, b.start_line, b.end_line
                   FROM semantic_mentions m JOIN blocks b ON b.id = m.block_id
                   JOIN documents d ON d.id = b.document_id
                   WHERE m.object_id = ? AND m.object_kind = ?
                   ORDER BY d.path, b.ordinal""",
                (object_id, kind),
            ).fetchall()
            if kind == "entity":
                item["aliases"] = [
                    value["alias"]
                    for value in conn.execute(
                        "SELECT alias FROM entity_aliases WHERE entity_id = ? ORDER BY alias COLLATE NOCASE",
                        (object_id,),
                    )
                ]
            related_rows = conn.execute(
                """SELECT r.id, r.relation_type, r.confidence, r.source_id, r.target_id,
                          r.block_id
                   FROM relations r WHERE r.source_id = ? OR r.target_id = ?
                   ORDER BY r.relation_type, r.id""",
                (object_id, object_id),
            ).fetchall()
            related = []
            other_ids = [
                relation["target_id"] if relation["source_id"] == object_id else relation["source_id"]
                for relation in related_rows
            ]
            name_map: dict[str, dict] = {}
            if other_ids:
                placeholders = ",".join("?" * len(other_ids))
                for other in conn.execute(
                    f"SELECT id, canonical_name, 'entity' AS kind FROM entities "
                    f"WHERE id IN ({placeholders}) AND status = 'active' "
                    f"UNION ALL SELECT id, canonical_name, 'concept' AS kind FROM concepts "
                    f"WHERE id IN ({placeholders}) AND status = 'active'",
                    (*other_ids, *other_ids),
                ):
                    name_map[other["id"]] = other
            for relation in related_rows:
                other_id = relation["target_id"] if relation["source_id"] == object_id else relation["source_id"]
                other = name_map.get(other_id)
                if other:
                    related.append(
                        {
                            "id": relation["id"],
                            "relation_type": relation["relation_type"],
                            "confidence": relation["confidence"],
                            "block_id": relation["block_id"],
                            "object_id": other_id,
                            "object_name": other["canonical_name"],
                            "object_kind": other["kind"],
                        }
                    )
            item["related"] = related
        audit_rows = conn.execute(
            """SELECT id, action, before_json, after_json, created_at
               FROM semantic_audit_log WHERE object_kind = ? AND object_id = ?
               ORDER BY created_at DESC LIMIT 20""",
            (kind, object_id),
        ).fetchall()
    item["sources"] = [evidence_row(value) for value in rows]
    item["verifications"] = store.claim_verifications(object_id) if kind == "claim" else []
    item["audit"] = [
        {
            "id": value["id"],
            "action": value["action"],
            "before": json.loads(value["before_json"] or "{}"),
            "after": json.loads(value["after_json"] or "{}"),
            "created_at": value["created_at"],
        }
        for value in audit_rows
    ]
    return {"success": True, "kind": kind, "item": item}


def list_semantic_objects(
    store: SemanticStore,
    tab: str,
    *,
    query: str,
    status: str,
    limit: int,
    offset: int,
    min_confidence: float | None = None,
) -> dict:
    """claims/concepts/entities 工作台分页列表（含验证快照与低频降级）。"""
    like = f"%{query}%"
    degraded_hidden = 0
    with store.connect() as conn:
        if tab == "claims":
            if status not in {"active", "deleted", "all"}:
                status = "active"
            status_clause = "" if status == "all" else "c.status = ? AND "
            args: tuple = (() if status == "all" else (status,)) + (query, like, like)
            evidence_clause = (
                "AND (c.status = 'deleted' OR EXISTS "
                "(SELECT 1 FROM evidence ae WHERE ae.claim_id = c.id AND ae.status = 'active'))"
            )
            where = f"WHERE {status_clause}(? = '' OR c.statement LIKE ? OR c.scope LIKE ?) {evidence_clause}"
            if min_confidence is not None:
                where += " AND c.confidence >= ?"
                args = (*args, min_confidence)
            total = conn.execute(f"SELECT count(*) FROM claims c {where}", args).fetchone()[0]
            rows = conn.execute(
                f"""SELECT c.id, c.statement, c.scope, c.claim_type, c.confidence, c.status,
                           sum(CASE WHEN e.status = 'active' THEN 1 ELSE 0 END) AS evidence_count,
                           sum(CASE WHEN e.status = 'excluded' THEN 1 ELSE 0 END) AS excluded_evidence_count,
                           v.verdict AS verification_verdict,
                           v.confidence AS verification_confidence,
                           v.method AS verification_method,
                           v.agent AS verification_agent,
                           v.created_at AS verified_at
                    FROM claims c LEFT JOIN evidence e ON e.claim_id = c.id
                    LEFT JOIN claim_verifications v ON v.id = (
                        SELECT v2.id FROM claim_verifications v2
                        WHERE v2.claim_id = c.id
                        ORDER BY v2.created_at DESC, v2.rowid DESC LIMIT 1
                    )
                    {where} GROUP BY c.id ORDER BY c.confidence DESC, c.statement LIMIT ? OFFSET ?""",
                (*args, limit, offset),
            ).fetchall()
            items = []
            claim_ids = [row["id"] for row in rows]
            evidence_by_claim: dict[str, list] = {}
            if claim_ids:
                placeholders = ",".join("?" * len(claim_ids))
                for ev in conn.execute(
                    f"""SELECT e.claim_id, e.id, e.status, d.path, d.title, d.topic, b.id AS block_id,
                              b.heading_path_json, b.content, b.start_line, b.end_line
                       FROM evidence e JOIN blocks b ON b.id = e.block_id
                       JOIN documents d ON d.id = b.document_id
                       WHERE e.claim_id IN ({placeholders}) ORDER BY d.path, b.ordinal""",
                    claim_ids,
                ):
                    evidence_by_claim.setdefault(ev["claim_id"], []).append(evidence_row(ev))
            for row in rows:
                item = dict(row)
                verdict = item.pop("verification_verdict", None)
                if verdict:
                    item["verification"] = {
                        "verdict": verdict,
                        "confidence": item.pop("verification_confidence"),
                        "method": item.pop("verification_method"),
                        "agent": item.pop("verification_agent"),
                        "verified_at": item.pop("verified_at"),
                    }
                else:
                    item.pop("verification_confidence", None)
                    item.pop("verification_method", None)
                    item.pop("verification_agent", None)
                    item.pop("verified_at", None)
                    item["verification"] = None
                item["evidence"] = evidence_by_claim.get(row["id"], [])
                items.append(item)
        else:
            table = tab
            kind = "concept" if tab == "concepts" else "entity"
            type_select = ", o.entity_type" if tab == "entities" else ""
            description_column = "o.description"
            where = "WHERE o.status = 'active' AND (? = '' OR o.canonical_name LIKE ? OR o.description LIKE ?)"
            args = (query, like, like)
            if min_confidence is not None:
                where += " AND o.confidence >= ?"
                args = (*args, min_confidence)
            # 低频降级：非 deep 强度且未主动搜索时，隐藏 mention<2 且
            # confidence<0.6 的对象（偶发提及，稀释列表但无代表性）。
            degrade_mentions = int(LOW_FREQ_DEGRADE["min_mentions"])
            degrade_confidence = float(LOW_FREQ_DEGRADE["min_confidence"])
            apply_degrade = min_confidence is not None and min_confidence > 0 and not query
            if apply_degrade:
                degraded_hidden = conn.execute(
                    f"""SELECT count(*) FROM {table} o
                        WHERE o.status = 'active'
                          AND o.confidence >= ? AND o.confidence < ?
                          AND (SELECT count(*) FROM semantic_mentions m
                               WHERE m.object_id = o.id AND m.object_kind = ?) < ?""",
                    (min_confidence, degrade_confidence, kind, degrade_mentions),
                ).fetchone()[0]
                where += (
                    " AND NOT (o.confidence < ? AND (SELECT count(*) FROM semantic_mentions m"
                    " WHERE m.object_id = o.id AND m.object_kind = ?) < ?)"
                )
                args = (*args, degrade_confidence, kind, degrade_mentions)
            total = conn.execute(f"SELECT count(*) FROM {table} o {where}", args).fetchone()[0]
            rows = conn.execute(
                f"""SELECT o.id, o.canonical_name, {description_column}, o.confidence{type_select},
                           count(m.block_id) AS mention_count,
                           count(DISTINCT b.document_id) AS source_count
                    FROM {table} o
                    LEFT JOIN semantic_mentions m ON m.object_id = o.id AND m.object_kind = ?
                    LEFT JOIN blocks b ON b.id = m.block_id
                    {where} GROUP BY o.id
                    ORDER BY mention_count DESC, o.canonical_name LIMIT ? OFFSET ?""",
                (kind, *args, limit, offset),
            ).fetchall()
            items = [dict(row) for row in rows]
    return {
        "success": True,
        "tab": tab,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "degraded_hidden": degraded_hidden,
    }
