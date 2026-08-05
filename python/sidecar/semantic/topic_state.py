"""Deterministic TopicState materialization from validated semantic facts."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sidecar.semantic.ids import content_hash, stable_id
from sidecar.semantic.store import SemanticStore


def build_topic_state(store: SemanticStore, topic: str) -> dict:
    topic_prefix = topic + " > "
    with store.connect() as conn:
        documents = list(
            conn.execute(
                """
                SELECT id, path, content_hash, title, topic
                FROM documents
                WHERE topic = ? OR instr(topic, ?) = 1
                ORDER BY path
                """,
                (topic, topic_prefix),
            )
        )
        claim_rows = list(
            conn.execute(
                """
                SELECT DISTINCT c.id, c.statement, c.scope, c.claim_type, c.confidence, d.topic
                FROM claims c
                JOIN evidence e ON e.claim_id = c.id
                JOIN blocks b ON b.id = e.block_id
                JOIN documents d ON d.id = b.document_id
                WHERE c.status = 'active' AND e.status = 'active'
                  AND (d.topic = ? OR instr(d.topic, ?) = 1)
                ORDER BY c.statement
                """,
                (topic, topic_prefix),
            )
        )
        # A claim may be evidenced by documents from several topics; DISTINCT
        # rows then repeat the claim id, so deduplicate while keeping order.
        seen_claim_ids: set[str] = set()
        claims: list[sqlite3.Row] = []
        for row in claim_rows:
            if row["id"] in seen_claim_ids:
                continue
            seen_claim_ids.add(row["id"])
            claims.append(row)
        evidence_rows = list(
            conn.execute(
                """
                SELECT e.claim_id, e.quote_hash, b.id AS block_id,
                       b.heading_path_json, b.start_line, b.end_line,
                       d.path AS document_path
                FROM evidence e
                JOIN blocks b ON b.id = e.block_id
                JOIN documents d ON d.id = b.document_id
                WHERE e.status = 'active' AND (d.topic = ? OR instr(d.topic, ?) = 1)
                ORDER BY d.path, b.ordinal
                """,
                (topic, topic_prefix),
            )
        )

    evidence_by_claim: dict[str, list[dict]] = {}
    for row in evidence_rows:
        evidence_by_claim.setdefault(row["claim_id"], []).append(
            {
                "document_path": row["document_path"],
                "block_id": row["block_id"],
                "heading_path": json.loads(row["heading_path_json"]),
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "quote_hash": row["quote_hash"],
            }
        )

    document_payload = [dict(row) for row in documents]
    claim_payload = [
        {
            **dict(row),
            "evidence": evidence_by_claim.get(row["id"], []),
        }
        for row in claims
        if evidence_by_claim.get(row["id"])
    ]
    input_hash = content_hash(
        json.dumps(
            {
                "documents": [(item["id"], item["content_hash"]) for item in document_payload],
                "claims": [(item["id"], [e["quote_hash"] for e in item["evidence"]]) for item in claim_payload],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return {
        "schema_version": 1,
        "topic_id": stable_id("top", topic.casefold()),
        "topic": topic,
        "input_hash": input_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": document_payload,
        "claims": claim_payload,
        "stats": {"documents": len(document_payload), "claims": len(claim_payload)},
    }


def materialize_topic_state(store: SemanticStore, topic: str) -> Path:
    state = build_topic_state(store, topic)
    target_dir = store.root / "topic_states"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{state['topic_id']}.json"
    data = json.dumps(state, ensure_ascii=False, indent=2)
    fd, temp_path = tempfile.mkstemp(dir=target_dir, prefix=f".{state['topic_id']}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    source_ids = (
        {item["id"] for item in state["documents"]}
        | {item["id"] for item in state["claims"]}
        | {evidence["block_id"] for claim in state["claims"] for evidence in claim["evidence"]}
    )
    store.replace_view_dependencies(
        view_id=state["topic_id"],
        view_kind="topic_state",
        input_hash=state["input_hash"],
        source_ids=source_ids,
    )
    return target
