"""Entity-quality inspection derived from the semantic SQLite snapshot.

Pure read-side derivation: issues are recomputed from current rows on every
call; review decisions persist in ``review_queue`` and are matched back by
stable issue id + content fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import re

from sidecar.semantic.store import SemanticStore
from sidecar.semantic.store_objects import name_fingerprint


def quality_key(*parts: str) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return "entity-quality-" + hashlib.sha256(payload).hexdigest()[:20]


def normalized_entity_name(value: str) -> str:
    return "".join(str(value or "").casefold().split())


def collect_quality_issues(store: SemanticStore) -> list[dict]:
    """Derive entity-quality issues from the current SQLite snapshot only."""
    with store.connect() as conn:
        entities = [
            dict(row)
            for row in conn.execute(
                "SELECT id, canonical_name, entity_type, description, confidence FROM entities WHERE status = 'active'"
            )
        ]
        mentions = {
            row["entity_id"]: int(row["count"])
            for row in conn.execute(
                """SELECT object_id AS entity_id, count(*) AS count FROM semantic_mentions
                   WHERE object_kind = 'entity' GROUP BY object_id"""
            )
        }
        linked = {
            row["entity_id"]
            for row in conn.execute(
                """SELECT source_id AS entity_id FROM relations
                   UNION SELECT target_id AS entity_id FROM relations"""
            )
        }
        aliases = [dict(row) for row in conn.execute("SELECT alias, entity_id FROM entity_aliases")]
        concepts = [
            dict(row) for row in conn.execute("SELECT id, canonical_name FROM concepts WHERE status = 'active'")
        ]
        concept_ids = {row["id"] for row in concepts}
        relation_endpoint_ids = {
            row["entity_id"]
            for row in conn.execute(
                "SELECT source_id AS entity_id FROM relations UNION SELECT target_id AS entity_id FROM relations"
            )
        }
        reviewed = {
            row["id"]: json.loads(row["payload_json"] or "{}")
            for row in conn.execute(
                "SELECT id, payload_json FROM review_queue WHERE item_kind = 'entity_quality' AND status = 'reviewed'"
            )
        }

    by_id = {entity["id"]: entity for entity in entities}
    concept_by_id = {concept["id"]: concept for concept in concepts}
    canonical_groups: dict[str, list[str]] = {}
    alias_groups: dict[str, list[str]] = {}
    concept_by_fp: dict[str, str] = {}
    for concept in concepts:
        concept_by_fp.setdefault(name_fingerprint(concept["canonical_name"]), concept["id"])
    # Relations legitimately link entities to concepts (RELATED_TO co-occurrence),
    # so concept endpoints must count as known. Only truly missing endpoints are dangling.
    dangling_relations = relation_endpoint_ids - set(by_id) - concept_ids
    for entity in entities:
        canonical_groups.setdefault(normalized_entity_name(entity["canonical_name"]), []).append(entity["id"])
    for alias in aliases:
        alias_groups.setdefault(normalized_entity_name(alias["alias"]), []).append(alias["entity_id"])

    issues: list[dict] = []

    def add(rule: str, entity: dict, reason: str, candidates: list[str] | None = None) -> None:
        candidate_ids = sorted(set(candidates or []))
        issue_id = quality_key(rule, entity["id"], *candidate_ids)
        fingerprint = quality_key(
            rule,
            entity["id"],
            entity["canonical_name"],
            str(entity["confidence"]),
            str(mentions.get(entity["id"], 0)),
            *candidate_ids,
        )
        persisted = reviewed.get(issue_id, {})
        status = "reviewed" if persisted.get("fingerprint") == fingerprint else "pending"
        candidate_names = []
        for value in candidate_ids:
            if value in by_id:
                candidate_names.append(by_id[value]["canonical_name"])
            elif value in concept_by_id:
                candidate_names.append(concept_by_id[value]["canonical_name"])
        issues.append(
            {
                "id": issue_id,
                "rule": rule,
                "entity_id": entity["id"],
                "entity_name": entity["canonical_name"],
                "entity_type": entity["entity_type"],
                "confidence": entity["confidence"],
                "mention_count": mentions.get(entity["id"], 0),
                "reason": reason,
                "candidate_ids": candidate_ids,
                "candidate_names": candidate_names,
                "candidate_kinds": [
                    "entity" if value in by_id else "concept"
                    for value in candidate_ids
                    if value in by_id or value in concept_by_id
                ],
                "fingerprint": fingerprint,
                "status": status,
            }
        )

    for entity in entities:
        entity_id = entity["id"]
        mention_count = mentions.get(entity_id, 0)
        if mention_count == 0:
            add("missing_source", entity, "当前实体没有关联的来源块")
        elif entity_id not in linked:
            add("isolated", entity, "实体只有来源出现，尚未建立受控语义关系")
        if float(entity["confidence"] or 0) < 0.6:
            add("low_confidence", entity, "实体抽取置信度低于 60%")
        if not str(entity["entity_type"] or "").strip():
            add("uncontrolled_type", entity, "实体缺少受控类型")
        if not str(entity.get("description") or "").strip():
            add("missing_description", entity, "实体缺少说明描述")

        # 全小写普通英文词 + 类型兜底 other：几乎不可能是具名对象
        # （合法库名 pandas/numpy/curl 的类型是 product/artifact，从不落 other）。
        name = str(entity["canonical_name"] or "")
        if entity["entity_type"] == "other" and re.fullmatch(r"[a-z]{3,12}", name):
            add("unlikely_entity_name", entity, "小写普通英文词被当作实体，疑似分类错误")

        name_key = normalized_entity_name(entity["canonical_name"])
        duplicate_ids = [value for value in canonical_groups.get(name_key, []) if value != entity_id]
        duplicate_ids += [value for value in alias_groups.get(name_key, []) if value != entity_id]
        duplicate_ids = sorted(set(duplicate_ids))
        if duplicate_ids:
            add("duplicate_candidate", entity, "规范名称或别名与其他实体重合，需人工确认", duplicate_ids)

        # 同名概念已存在：同一名字不应同时出现在实体与概念两表。
        cross_kind_id = concept_by_fp.get(name_fingerprint(entity["canonical_name"]))
        if cross_kind_id is not None:
            add("cross_kind_duplicate", entity, "同名概念已存在，需确认合并到实体或概念", [cross_kind_id])

    for alias_key, entity_ids in alias_groups.items():
        normalized_ids = sorted(set(entity_ids))
        if len(normalized_ids) > 1:
            for entity_id in normalized_ids:
                matched_entity = by_id.get(entity_id)
                if matched_entity:
                    add(
                        "alias_conflict",
                        matched_entity,
                        "同一别名映射到多个规范实体",
                        [value for value in normalized_ids if value != entity_id],
                    )

    for dangling_id in sorted(dangling_relations):
        # Attach an orphaned relation to the first entity only as a visible
        # repair signal; the relation ID itself remains untouched.
        if entities:
            add("dangling_relation", entities[0], f"发现关系端点「{dangling_id}」已不存在")
    return sorted(issues, key=lambda item: (item["status"] != "pending", item["rule"], item["entity_name"]))
