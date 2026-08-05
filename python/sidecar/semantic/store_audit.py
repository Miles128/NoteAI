"""Change-log audit queries (semantic store family)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sidecar.semantic.store_base import SemanticStoreBase

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS semantic_audit_log (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    object_id TEXT NOT NULL,
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_semantic_audit_object
    ON semantic_audit_log(object_kind, object_id, created_at DESC);
CREATE TABLE IF NOT EXISTS semantic_change_log (
    id TEXT PRIMARY KEY,
    change_kind TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    object_id TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    source_path TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_semantic_change_created
    ON semantic_change_log(created_at DESC);
"""


class AuditStore(SemanticStoreBase):
    """semantic_audit_log / semantic_change_log 的变更审计只读查询。"""

    schema_sql = AUDIT_SCHEMA

    def __init__(self, facade: SemanticStoreBase):
        super().__init__(facade.workspace)
        self._facade = facade

    def initialize(self) -> None:
        self._facade.initialize()

    def change_counts(self, *, days: int = 7) -> list[dict]:
        """Aggregate change events per kind inside the window (read-only)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.connect() as conn:
            self._ensure_change_log(conn)
            rows = conn.execute(
                """SELECT change_kind, object_kind, count(*) AS count
                   FROM semantic_change_log WHERE created_at >= ?
                   GROUP BY change_kind, object_kind""",
                (cutoff,),
            ).fetchall()
        return [
            {"change_kind": row["change_kind"], "object_kind": row["object_kind"], "count": row["count"]}
            for row in rows
        ]

    def recent_changes(
        self,
        *,
        days: int = 7,
        limit: int = 100,
        offset: int = 0,
        object_kind: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return recent change events newest-first (read-only)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        where = "created_at >= ?"
        args: list = [cutoff]
        if object_kind:
            where += " AND object_kind = ?"
            args.append(object_kind)
        with self.connect() as conn:
            self._ensure_change_log(conn)
            total = conn.execute(f"SELECT count(*) FROM semantic_change_log WHERE {where}", args).fetchone()[0]
            rows = conn.execute(
                f"""SELECT change_kind, object_kind, object_id, label, detail_json,
                           source_path, topic, created_at
                    FROM semantic_change_log WHERE {where}
                    ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?""",
                [*args, limit, offset],
            ).fetchall()
        items = [
            {
                "change_kind": row["change_kind"],
                "object_kind": row["object_kind"],
                "object_id": row["object_id"],
                "label": row["label"],
                "detail": json.loads(row["detail_json"] or "{}"),
                "source_path": row["source_path"],
                "topic": row["topic"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        return items, total

    def topics_with_changes(self, *, days: int = 7, limit: int = 50) -> list[str]:
        """Topics that have change-log rows inside the window, newest first (read-only)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.connect() as conn:
            self._ensure_change_log(conn)
            rows = conn.execute(
                """SELECT topic, max(created_at) AS last_seen FROM semantic_change_log
                   WHERE created_at >= ? AND topic != ''
                   GROUP BY topic ORDER BY last_seen DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [row["topic"] for row in rows]

    def topic_changes(
        self,
        *,
        topic: str,
        days: int = 7,
        limit: int = 60,
    ) -> list[dict]:
        """Change-log rows for one topic inside the window, newest first (read-only)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.connect() as conn:
            self._ensure_change_log(conn)
            rows = conn.execute(
                """SELECT change_kind, object_kind, object_id, label, detail_json,
                           source_path, topic, created_at
                    FROM semantic_change_log
                    WHERE created_at >= ? AND topic = ?
                    ORDER BY created_at DESC, rowid DESC LIMIT ?""",
                (cutoff, topic, limit),
            ).fetchall()
        return [
            {
                "change_kind": row["change_kind"],
                "object_kind": row["object_kind"],
                "object_id": row["object_id"],
                "label": row["label"],
                "detail": json.loads(row["detail_json"] or "{}"),
                "source_path": row["source_path"],
                "topic": row["topic"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
