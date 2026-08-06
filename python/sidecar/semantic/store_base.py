"""Shared SQLite connection management for the semantic store family.

``SemanticStoreBase`` owns connection creation, the transaction context and
the cross-family audit/change-log helpers.  The per-family stores
(documents/objects/claims/audit) inherit it; the ``SemanticStore`` facade
orchestrates schema initialization order across all families.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from config.settings import WORKSPACE_APP_FOLDER

SCHEMA_VERSION = 5
CLAIM_POLICY_VERSION = 6
# 抽取指纹算法版本：变更 name_fingerprint 算法时递增，initialize() 会全量重算
# 存量对象的 name_fingerprint（如 v2 → v3 的标点变体归一：DALL-E/DALL·E）。
FINGERPRINT_ALGORITHM_VERSION = 3
CHANGE_LOG_LIMIT = 8000

# 不属于任何单一表族的基础设施表（元信息、编译运行记录、物化视图依赖、审阅队列）。
CORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compile_runs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    stats_json TEXT NOT NULL DEFAULT '{}',
    error TEXT
);
CREATE TABLE IF NOT EXISTS dependencies (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    PRIMARY KEY(source_id, target_id, target_kind)
);
CREATE TABLE IF NOT EXISTS review_queue (
    id TEXT PRIMARY KEY,
    item_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
"""


class SemanticStoreBase:
    """Connection lifecycle + shared write helpers for all semantic stores.

    Every public operation opens its own connection via :meth:`connect`
    (per-operation connection, committed/rolled back and closed on exit), so
    the store stays safe under the sidecar's multi-threaded RPC usage — the
    same semantics the original monolithic ``SemanticStore`` provided.
    """

    #: Schema DDL contributed by this store family; subclasses override it.
    #: The facade concatenates every family's DDL before executescript.
    schema_sql: str = ""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.root = self.workspace / WORKSPACE_APP_FOLDER / "compiler"
        self.path = self.root / "semantic.db"

    def initialize(self) -> None:
        """Ensure schema + migrations. Overridden by the facade to orchestrate
        every family's migrations in order; sub-stores forward to the facade.
        """
        raise NotImplementedError

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _record_change(
        conn: sqlite3.Connection,
        *,
        change_kind: str,
        object_kind: str,
        object_id: str,
        label: str = "",
        detail: dict | None = None,
        source_path: str = "",
        topic: str = "",
    ) -> None:
        """Append one knowledge-change event (added/updated/invalidated/removed)."""
        conn.execute(
            """INSERT INTO semantic_change_log(
                   id, change_kind, object_kind, object_id, label,
                   detail_json, source_path, topic, created_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uuid4().hex,
                change_kind,
                object_kind,
                object_id,
                label,
                json.dumps(detail or {}, ensure_ascii=False),
                source_path,
                topic,
                SemanticStoreBase._now(),
            ),
        )

    @staticmethod
    def _ensure_change_log(conn: sqlite3.Connection) -> None:
        """Create the change log on legacy databases predating this table.

        Uses only CREATE IF NOT EXISTS so read-only workbench queries can
        repair stale stores without touching compiled knowledge rows.
        """
        conn.execute(
            """CREATE TABLE IF NOT EXISTS semantic_change_log (
                id TEXT PRIMARY KEY,
                change_kind TEXT NOT NULL,
                object_kind TEXT NOT NULL,
                object_id TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                detail_json TEXT NOT NULL DEFAULT '{}',
                source_path TEXT NOT NULL DEFAULT '',
                topic TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_change_created ON semantic_change_log(created_at DESC)")

    @staticmethod
    def _trim_change_log(conn: sqlite3.Connection) -> None:
        count = conn.execute("SELECT count(*) FROM semantic_change_log").fetchone()[0]
        if count > CHANGE_LOG_LIMIT + 2000:
            conn.execute(
                """DELETE FROM semantic_change_log WHERE id NOT IN (
                       SELECT id FROM semantic_change_log
                       ORDER BY created_at DESC, rowid DESC LIMIT ?
                   )""",
                (CHANGE_LOG_LIMIT,),
            )

    @staticmethod
    def _block_source(conn: sqlite3.Connection, block_id: str) -> tuple[str, str]:
        row = conn.execute(
            """SELECT d.path AS path, d.topic AS topic
               FROM blocks b JOIN documents d ON d.id = b.document_id
               WHERE b.id = ?""",
            (block_id,),
        ).fetchone()
        if row is None:
            return "", ""
        return str(row["path"] or ""), str(row["topic"] or "")

    @staticmethod
    def _invalidate_orphan_claims(
        conn: sqlite3.Connection,
        *,
        reason: str,
        source_path: str = "",
        topic: str = "",
        detail: dict | None = None,
    ) -> int:
        """Record then delete claims that lost their last supporting evidence."""
        orphans = conn.execute(
            """SELECT c.id AS id, c.statement AS statement FROM claims c
               WHERE NOT EXISTS (SELECT 1 FROM evidence e WHERE e.claim_id = c.id)"""
        ).fetchall()
        payload = {"reason": reason}
        if detail:
            payload.update(detail)
        for row in orphans:
            SemanticStoreBase._record_change(
                conn,
                change_kind="invalidated",
                object_kind="claim",
                object_id=row["id"],
                label=row["statement"],
                detail=payload,
                source_path=source_path,
                topic=topic,
            )
        if orphans:
            conn.execute(
                """DELETE FROM claims
                   WHERE NOT EXISTS (SELECT 1 FROM evidence WHERE evidence.claim_id = claims.id)"""
            )
        return len(orphans)

    @staticmethod
    def _audit(
        conn: sqlite3.Connection,
        *,
        action: str,
        object_kind: str,
        object_id: str,
        before: dict,
        after: dict,
    ) -> None:
        conn.execute(
            """INSERT INTO semantic_audit_log(
                   id, action, object_kind, object_id, before_json, after_json, created_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (
                uuid4().hex,
                action,
                object_kind,
                object_id,
                json.dumps(before, ensure_ascii=False, sort_keys=True),
                json.dumps(after, ensure_ascii=False, sort_keys=True),
                SemanticStoreBase._now(),
            ),
        )
