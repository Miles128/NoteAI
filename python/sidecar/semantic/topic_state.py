"""Deterministic TopicState materialization from extracted semantic objects."""

from __future__ import annotations

import json
import os
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
        object_rows = list(
            conn.execute(
                """
                SELECT DISTINCT m.object_id AS id, m.object_kind AS kind, d.topic AS topic
                FROM semantic_mentions m
                JOIN blocks b ON b.id = m.block_id
                JOIN documents d ON d.id = b.document_id
                WHERE d.topic = ? OR instr(d.topic, ?) = 1
                ORDER BY m.object_kind, m.object_id
                """,
                (topic, topic_prefix),
            )
        )

    document_payload = [dict(row) for row in documents]
    object_payload = [dict(row) for row in object_rows]
    input_hash = content_hash(
        json.dumps(
            {
                "documents": [(item["id"], item["content_hash"]) for item in document_payload],
                "objects": [(item["kind"], item["id"]) for item in object_payload],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return {
        "schema_version": 2,
        "topic_id": stable_id("top", topic.casefold()),
        "topic": topic,
        "input_hash": input_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": document_payload,
        "objects": object_payload,
        "stats": {
            "documents": len(document_payload),
            "objects": len(object_payload),
        },
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
    source_ids = {item["id"] for item in state["documents"]} | {item["id"] for item in state["objects"]}
    store.replace_view_dependencies(
        view_id=state["topic_id"],
        view_kind="topic_state",
        input_hash=state["input_hash"],
        source_ids=source_ids,
    )
    return target
