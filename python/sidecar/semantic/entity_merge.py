"""Manual entity merge workflow for the semantic workbench.

Handler-side flow orchestration (parameter validation, response envelope) stays
in ``semantic_handler``; this module owns the merge transaction itself and the
follow-up semantic-page rebuilds. Data-level duplicate merging lives separately
in ``store_objects.merge_duplicate_entities`` and is intentionally not shared.
"""

from __future__ import annotations

from sidecar.semantic.ids import stable_id
from sidecar.semantic.store import SemanticStore


def merge_entities(store: SemanticStore, source_id: str, target_id: str) -> dict:
    """Merge ``source_id`` into ``target_id`` in one transaction, then rebuild
    the affected semantic pages. Returns the RPC-ready result dict.
    """
    affected_topics: set[str] = set()
    affected_concept_ids: set[str] = set()
    with store.connect() as conn:
        rows = conn.execute("SELECT * FROM entities WHERE id IN (?, ?)", (source_id, target_id)).fetchall()
        if len(rows) != 2:
            return {"success": False, "message": "实体不存在"}
        entities = {row["id"]: dict(row) for row in rows}
        source, target = entities[source_id], entities[target_id]
        before = {"source": source, "target": target}
        # Preserve every unique mention while avoiding the composite-PK collision.
        conn.execute(
            """DELETE FROM semantic_mentions WHERE object_id = ? AND object_kind = 'entity'
               AND block_id IN (SELECT block_id FROM semantic_mentions WHERE object_id = ? AND object_kind = 'entity')""",
            (source_id, target_id),
        )
        conn.execute(
            "UPDATE semantic_mentions SET object_id = ? WHERE object_id = ? AND object_kind = 'entity'",
            (target_id, source_id),
        )
        aliases = [
            row["alias"] for row in conn.execute("SELECT alias FROM entity_aliases WHERE entity_id = ?", (source_id,))
        ]
        if source["canonical_name"].casefold() != target["canonical_name"].casefold():
            aliases.append(source["canonical_name"])
        for alias in aliases:
            existing = conn.execute(
                "SELECT entity_id FROM entity_aliases WHERE alias = ? COLLATE NOCASE", (alias,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO entity_aliases(alias, entity_id, created_at) VALUES(?, ?, ?)",
                    (alias, target_id, store._now()),
                )
            elif existing["entity_id"] == source_id:
                conn.execute(
                    "UPDATE entity_aliases SET entity_id = ? WHERE alias = ? COLLATE NOCASE", (target_id, alias)
                )
        conn.execute("UPDATE relations SET source_id = ? WHERE source_id = ?", (target_id, source_id))
        conn.execute("UPDATE relations SET target_id = ? WHERE target_id = ?", (target_id, source_id))
        # Re-key only relations touched by this merge. The former unscoped
        # `source_id = target_id` delete removed every self-loop in the DB,
        # including relations belonging to unrelated entities.
        touched_relations = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM relations WHERE source_id = ? OR target_id = ?",
                (target_id, target_id),
            )
        ]
        conn.executemany(
            "DELETE FROM relations WHERE id = ?",
            ((row["id"],) for row in touched_relations),
        )
        deduplicated_relations: dict[tuple, dict] = {}
        for relation in touched_relations:
            if relation["source_id"] == relation["target_id"]:
                continue
            key = (
                relation["source_id"],
                relation["relation_type"],
                relation["target_id"],
                relation.get("evidence_id"),
                relation.get("block_id"),
            )
            current = deduplicated_relations.get(key)
            if current is None or float(relation["confidence"]) > float(current["confidence"]):
                deduplicated_relations[key] = relation
        for relation in deduplicated_relations.values():
            origin_id = relation.get("block_id") or relation.get("evidence_id") or relation["id"]
            relation_id = stable_id(
                "relation",
                origin_id,
                relation["source_id"],
                relation["relation_type"],
                relation["target_id"],
            )
            conn.execute(
                """INSERT INTO relations(
                       id, source_id, relation_type, target_id, confidence, evidence_id, block_id
                   ) VALUES(?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET confidence = MAX(relations.confidence, excluded.confidence),
                                                evidence_id = excluded.evidence_id,
                                                block_id = excluded.block_id""",
                (
                    relation_id,
                    relation["source_id"],
                    relation["relation_type"],
                    relation["target_id"],
                    relation["confidence"],
                    relation.get("evidence_id"),
                    relation.get("block_id"),
                ),
            )
        conn.execute(
            "UPDATE review_queue SET status = 'reviewed' WHERE item_kind = 'entity_quality' AND payload_json LIKE ?",
            (f'%"entity_id": "{source_id}"%',),
        )
        conn.execute("DELETE FROM entities WHERE id = ?", (source_id,))
        affected_topics = {
            row["topic"]
            for row in conn.execute(
                """SELECT DISTINCT d.topic FROM semantic_mentions m
                   JOIN blocks b ON b.id = m.block_id JOIN documents d ON d.id = b.document_id
                   WHERE m.object_id = ? AND m.object_kind = 'entity' AND d.topic != ''""",
                (target_id,),
            )
        }
        related_ids = {
            row["other_id"]
            for row in conn.execute(
                """SELECT CASE WHEN source_id = ? THEN target_id ELSE source_id END AS other_id
                   FROM relations WHERE source_id = ? OR target_id = ?""",
                (target_id, target_id, target_id),
            )
        }
        affected_concept_ids = (
            {
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM concepts WHERE id IN ({}) AND status = 'active'".format(
                        ",".join("?" for _ in related_ids) or "''"
                    ),
                    tuple(related_ids),
                )
            }
            if related_ids
            else set()
        )
        after = {"merged_into": target_id, "source_id": source_id, "aliases_added": aliases}
        SemanticStore._audit(
            conn, action="merge_entity", object_kind="entity", object_id=target_id, before=before, after=after
        )
    materialized = []
    try:
        from sidecar.semantic.object_wiki import materialize_object_collection
        from sidecar.semantic.topic_state import materialize_topic_state
        from sidecar.semantic.wiki import materialize_topic_wiki_page

        for topic in sorted(affected_topics):
            materialize_topic_state(store, topic)
            materialize_topic_wiki_page(store, topic)
            materialized.append(topic)
        materialize_object_collection(store, "entity")
        if affected_concept_ids:
            materialize_object_collection(store, "concept")
    except OSError as exc:
        return {"success": False, "message": f"实体已合并，但语义页重建失败：{exc}"}
    return {
        "success": True,
        "target_id": target_id,
        "affected_topics": materialized,
        "message": f"已将「{source['canonical_name']}」合并到「{target['canonical_name']}」",
    }
