"""Automatic, dependency-scoped publishing of semantic derived views."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar

from sidecar.semantic.object_wiki import materialize_object_collection
from sidecar.semantic.store import SemanticStore
from sidecar.semantic.topic_state import materialize_topic_state
from sidecar.semantic.wiki import materialize_topic_wiki_page

_LOCK_RETRIES = 4
_LOCK_DELAY = 0.05
_T = TypeVar("_T")


def _retry_lock(operation: Callable[[], _T]) -> _T:
    for attempt in range(_LOCK_RETRIES):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == _LOCK_RETRIES - 1:
                raise
            time.sleep(_LOCK_DELAY * (2**attempt))
    raise AssertionError("unreachable")


def materialize_documents(
    store: SemanticStore,
    document_ids: set[str],
    *,
    previous_objects: list[dict] | None = None,
    affected_topics: set[str] | None = None,
    include_objects: bool = True,
) -> dict:
    """Refresh only views touched by the supplied source documents.

    This is deliberately best-effort: every page writer uses atomic replacement,
    so one failed derived view leaves its previous usable version intact and does
    not roll back successful semantic extraction.
    """
    previous_objects = previous_objects or []
    topics = set(affected_topics or set())
    objects: dict[tuple[str, str], dict] = {
        (str(item["kind"]), str(item["id"])): dict(item)
        for item in previous_objects
        if item.get("kind") in {"entity", "concept"} and item.get("id") and item.get("name")
    }

    if document_ids:
        placeholders = ",".join("?" for _ in document_ids)

        def load_inputs() -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
            with store.connect() as conn:
                topic_rows = list(conn.execute(
                    f"SELECT DISTINCT topic FROM documents WHERE id IN ({placeholders}) AND topic != ''",
                    tuple(sorted(document_ids)),
                ))
                object_rows = list(conn.execute(
                    f"""SELECT DISTINCT m.object_kind AS kind, m.object_id AS id,
                               CASE m.object_kind
                                   WHEN 'entity' THEN e.canonical_name
                                   ELSE c.canonical_name
                               END AS name
                        FROM semantic_mentions m
                        JOIN blocks b ON b.id = m.block_id
                        LEFT JOIN entities e
                          ON m.object_kind = 'entity' AND e.id = m.object_id
                        LEFT JOIN concepts c
                          ON m.object_kind = 'concept' AND c.id = m.object_id
                        WHERE b.document_id IN ({placeholders})
                          AND m.object_kind IN ('entity', 'concept')""",
                    tuple(sorted(document_ids)),
                ))
            return topic_rows, object_rows

        try:
            topic_rows, object_rows = _retry_lock(load_inputs)
            topics.update(row["topic"] for row in topic_rows)
            if include_objects:
                for object_row in object_rows:
                    if object_row["name"]:
                        objects[(object_row["kind"], object_row["id"])] = dict(object_row)
        except (OSError, ValueError, sqlite3.Error) as exc:
            return {
                "entities": 0,
                "concepts": 0,
                "topics": 0,
                "removed": {"entities": 0, "concepts": 0},
                "failures": [{"kind": "inputs", "id": "documents", "error": str(exc)}],
            }

    result: dict[str, Any] = {
        "entities": 0,
        "concepts": 0,
        "topics": 0,
        "removed": {"entities": 0, "concepts": 0},
        "failures": [],
    }
    if not include_objects:
        objects.clear()
    dirty_kinds: set[str] = set()
    for object_data in objects.values():
        kind = object_data["kind"]
        object_id = object_data["id"]
        dirty_kinds.add(kind)
        try:
            table = "entities" if kind == "entity" else "concepts"

            def load_source_count(
                table: str = table,
                object_id: str = object_id,
                kind: str = kind,
            ) -> tuple[sqlite3.Row | None, int]:
                with store.connect() as conn:
                    current = conn.execute(
                        f"SELECT canonical_name FROM {table} WHERE id = ? AND status = 'active'",
                        (object_id,),
                    ).fetchone()
                    source_count = conn.execute(
                        "SELECT COUNT(*) FROM semantic_mentions WHERE object_id = ? AND object_kind = ?",
                        (object_id, kind),
                    ).fetchone()[0]
                return current, source_count

            current, source_count = _retry_lock(load_source_count)
            if current is None or not source_count:
                result["removed"]["entities" if kind == "entity" else "concepts"] += 1
                continue
            result["entities" if kind == "entity" else "concepts"] += 1
        except (OSError, ValueError, sqlite3.Error) as exc:
            result["failures"].append({"kind": kind, "id": object_id, "error": str(exc)})
    for kind in sorted(dirty_kinds):
        try:
            _retry_lock(partial(materialize_object_collection, store, kind))
        except (OSError, ValueError, sqlite3.Error) as exc:
            result["failures"].append(
                {"kind": f"{kind}_collection", "id": kind, "error": str(exc)}
            )
    for topic in sorted(topics):
        try:
            _retry_lock(partial(materialize_topic_state, store, topic))
            _retry_lock(partial(materialize_topic_wiki_page, store, topic))
            result["topics"] += 1
        except (OSError, ValueError, sqlite3.Error) as exc:
            result["failures"].append({"kind": "topic", "id": topic, "error": str(exc)})
    return result
