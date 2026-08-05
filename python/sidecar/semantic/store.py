"""Transactional SQLite storage for semantic compiler state."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from config.settings import WORKSPACE_APP_FOLDER
from sidecar.semantic.ids import stable_id

SCHEMA_VERSION = 5
CLAIM_POLICY_VERSION = 6

_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'parsed',
    compiled_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blocks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    block_type TEXT NOT NULL,
    heading_path_json TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blocks_document ON blocks(document_id, ordinal);
CREATE TABLE IF NOT EXISTS concepts (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '',
    claim_type TEXT NOT NULL CHECK(claim_type IN ('conclusion', 'hypothesis')),
    confidence REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    user_edited INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    quote_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    UNIQUE(claim_id, block_id, quote_hash)
);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_block ON evidence(block_id);
CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_id TEXT REFERENCES evidence(id) ON DELETE SET NULL,
    block_id TEXT REFERENCES blocks(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS semantic_mentions (
    object_id TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    PRIMARY KEY(object_id, object_kind, block_id)
);
CREATE TABLE IF NOT EXISTS block_extractions (
    block_id TEXT PRIMARY KEY REFERENCES blocks(id) ON DELETE CASCADE,
    block_hash TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS claim_extractions (
    block_id TEXT PRIMARY KEY REFERENCES blocks(id) ON DELETE CASCADE,
    block_hash TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
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
CREATE TABLE IF NOT EXISTS entity_aliases (
    alias TEXT PRIMARY KEY COLLATE NOCASE,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);
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
CREATE TABLE IF NOT EXISTS claim_verifications (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL CHECK(verdict IN ('supported', 'refuted', 'unclear')),
    confidence REAL NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT 'default',
    agent TEXT NOT NULL DEFAULT '',
    sources_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claim_verifications_claim
    ON claim_verifications(claim_id, created_at DESC);
"""

CHANGE_LOG_LIMIT = 8000

_PAREN_PAIR_RE = re.compile(r"[（(][^（()）]*[)）]")


def name_fingerprint(name: str) -> str:
    """Normalize an object name for duplicate detection at extraction time.

    Strips parenthetical annotations (``RAG（检索增强生成）`` → ``RAG``), all
    whitespace and case, so variant spellings of the same object resolve to
    the same fingerprint and merge into one row instead of duplicating.
    """
    text = _PAREN_PAIR_RE.sub("", name)
    fp = "".join(text.casefold().split())
    return fp or "".join(name.casefold().split())


class SemanticStore:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.root = self.workspace / WORKSPACE_APP_FOLDER / "compiler"
        self.path = self.root / "semantic.db"

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            # Set the journal mode only during explicit schema initialization.
            # Repeating this PRAGMA on every read connection can contend with an
            # active compiler transaction and make otherwise read-only RPCs wait.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA)
            claim_columns = {row["name"] for row in conn.execute("PRAGMA table_info(claims)")}
            if "claim_type" not in claim_columns:
                conn.execute(
                    "ALTER TABLE claims ADD COLUMN claim_type TEXT NOT NULL DEFAULT 'conclusion' "
                    "CHECK(claim_type IN ('conclusion', 'hypothesis'))"
                )
            if "user_edited" not in claim_columns:
                conn.execute("ALTER TABLE claims ADD COLUMN user_edited INTEGER NOT NULL DEFAULT 0")
            evidence_columns = {row["name"] for row in conn.execute("PRAGMA table_info(evidence)")}
            if "status" not in evidence_columns:
                conn.execute("ALTER TABLE evidence ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            relation_columns = {row["name"] for row in conn.execute("PRAGMA table_info(relations)")}
            if "block_id" not in relation_columns:
                # Co-occurrence relations are derived per block.  Keeping the
                # origin lets a later extraction replace exactly its own edges.
                conn.execute("ALTER TABLE relations ADD COLUMN block_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_block ON relations(block_id)")
            # Extraction-time duplicate detection: a name fingerprint column
            # lets variant spellings (parenthetical annotations, whitespace,
            # case) merge into the existing row the moment a block is saved.
            for table in ("entities", "concepts"):
                cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
                if "name_fingerprint" not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN name_fingerprint TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_fp ON entities(name_fingerprint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_concepts_fp ON concepts(name_fingerprint)")
            for table in ("entities", "concepts"):
                rows = conn.execute(f"SELECT id, canonical_name FROM {table} WHERE name_fingerprint IS NULL").fetchall()
                for row in rows:
                    conn.execute(
                        f"UPDATE {table} SET name_fingerprint = ? WHERE id = ?",
                        (name_fingerprint(row["canonical_name"]), row["id"]),
                    )
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            row = conn.execute("SELECT value FROM schema_meta WHERE key = 'claim_policy_version'").fetchone()
            if row is None or row["value"] != str(CLAIM_POLICY_VERSION):
                # Claims/Evidence are derived data. A policy change invalidates
                # every legacy claim so old broad extraction cannot leak into
                # the stricter conclusion/hypothesis workbench.
                conn.execute(
                    """DELETE FROM relations
                       WHERE evidence_id IN (SELECT id FROM evidence)
                          OR source_id IN (SELECT id FROM claims)
                          OR target_id IN (SELECT id FROM claims)"""
                )
                conn.execute("DELETE FROM semantic_mentions WHERE object_kind = 'claim'")
                conn.execute("DELETE FROM evidence")
                conn.execute("DELETE FROM claims")
                conn.execute("DELETE FROM claim_extractions")
                conn.execute("UPDATE documents SET status = 'parsed' WHERE status IN ('semantic', 'partial')")
                conn.execute(
                    "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('claim_policy_version', ?)",
                    (str(CLAIM_POLICY_VERSION),),
                )

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
                SemanticStore._now(),
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
            SemanticStore._record_change(
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
                SemanticStore._now(),
            ),
        )

    def update_claim(
        self,
        claim_id: str,
        *,
        statement: str,
        scope: str,
        claim_type: str,
    ) -> dict | None:
        if claim_type not in {"conclusion", "hypothesis"}:
            raise ValueError("unsupported claim type")
        statement = statement.strip()
        scope = scope.strip()
        if not statement:
            raise ValueError("claim statement is required")
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
            if row is None:
                return None
            before = dict(row)
            conn.execute(
                "UPDATE claims SET statement = ?, scope = ?, claim_type = ?, user_edited = 1 WHERE id = ?",
                (statement, scope, claim_type, claim_id),
            )
            after = {
                **before,
                "statement": statement,
                "scope": scope,
                "claim_type": claim_type,
                "user_edited": 1,
            }
            self._audit(
                conn,
                action="edit",
                object_kind="claim",
                object_id=claim_id,
                before=before,
                after=after,
            )
            return after

    def set_claim_status(self, claim_id: str, status: str) -> dict | None:
        if status not in {"active", "deleted"}:
            raise ValueError("unsupported claim status")
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
            if row is None:
                return None
            before = dict(row)
            if before["status"] == status:
                return before
            conn.execute("UPDATE claims SET status = ? WHERE id = ?", (status, claim_id))
            after = {**before, "status": status}
            self._audit(
                conn,
                action="delete" if status == "deleted" else "restore",
                object_kind="claim",
                object_id=claim_id,
                before=before,
                after=after,
            )
            return after

    def save_claim_verification(
        self,
        claim_id: str,
        *,
        verdict: str,
        confidence: float,
        summary: str = "",
        method: str = "default",
        agent: str = "",
        sources: list[dict] | None = None,
    ) -> dict | None:
        """Persist one external verification result (联网证实/证伪) for a claim."""
        if verdict not in {"supported", "refuted", "unclear"}:
            raise ValueError("unsupported verdict")
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence 必须是数字") from exc
        sources = [source for source in (sources or []) if isinstance(source, dict)]
        created_at = self._now()
        verification_id = stable_id("cvr", claim_id, created_at)
        with self.connect() as conn:
            claim = conn.execute("SELECT id, statement FROM claims WHERE id = ?", (claim_id,)).fetchone()
            if claim is None:
                return None
            conn.execute(
                """INSERT INTO claim_verifications(
                       id, claim_id, verdict, confidence, summary, method, agent, sources_json, created_at
                   ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    verification_id,
                    claim_id,
                    verdict,
                    confidence,
                    (summary or "").strip(),
                    method,
                    agent,
                    json.dumps(sources, ensure_ascii=False),
                    created_at,
                ),
            )
            self._audit(
                conn,
                action="verify_claim",
                object_kind="claim",
                object_id=claim_id,
                before={},
                after={
                    "verdict": verdict,
                    "confidence": confidence,
                    "method": method,
                    "agent": agent,
                    "sources": len(sources),
                },
            )
        return {
            "id": verification_id,
            "claim_id": claim_id,
            "verdict": verdict,
            "confidence": confidence,
            "summary": (summary or "").strip(),
            "method": method,
            "agent": agent,
            "sources": sources,
            "created_at": created_at,
        }

    def set_evidence_status(self, evidence_id: str, status: str) -> dict | None:
        if status not in {"active", "excluded"}:
            raise ValueError("unsupported evidence status")
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,)).fetchone()
            if row is None:
                return None
            before = dict(row)
            if before["status"] == status:
                return before
            conn.execute("UPDATE evidence SET status = ? WHERE id = ?", (status, evidence_id))
            after = {**before, "status": status}
            self._audit(
                conn,
                action="exclude" if status == "excluded" else "restore",
                object_kind="evidence",
                object_id=evidence_id,
                before=before,
                after=after,
            )
            return after

    def claim_verifications(self, claim_id: str, *, limit: int = 10) -> list[dict]:
        """Return verification history for one claim, newest first (read-only)."""
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id, claim_id, verdict, confidence, summary, method, agent,
                          sources_json, created_at
                   FROM claim_verifications WHERE claim_id = ?
                   ORDER BY created_at DESC, rowid DESC LIMIT ?""",
                (claim_id, max(1, limit)),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "claim_id": row["claim_id"],
                "verdict": row["verdict"],
                "confidence": row["confidence"],
                "summary": row["summary"],
                "method": row["method"],
                "agent": row["agent"],
                "sources": json.loads(row["sources_json"] or "[]"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def latest_claim_verification(self, claim_id: str) -> dict | None:
        """Return the most recent verification for one claim (read-only)."""
        items = self.claim_verifications(claim_id, limit=1)
        return items[0] if items else None

    def list_claims_for_verification(
        self,
        *,
        topic: str | None = None,
        limit: int | None = None,
        verified: bool | None = None,
    ) -> list[dict]:
        """List active evidenced claims with their latest verification (read-only).

        ``verified`` filters by whether a claim already has any verification:
        ``True`` only verified, ``False`` only unverified, ``None`` all.
        """
        where = [
            "c.status = 'active'",
            "EXISTS (SELECT 1 FROM evidence e WHERE e.claim_id = c.id AND e.status = 'active')",
        ]
        args: list[object] = []
        if topic:
            where.append(
                "EXISTS (SELECT 1 FROM evidence e2 JOIN blocks b2 ON b2.id = e2.block_id "
                "JOIN documents d2 ON d2.id = b2.document_id "
                "WHERE e2.claim_id = c.id AND d2.topic = ?)"
            )
            args.append(topic)
        if verified is True:
            where.append("EXISTS (SELECT 1 FROM claim_verifications v WHERE v.claim_id = c.id)")
        elif verified is False:
            where.append("NOT EXISTS (SELECT 1 FROM claim_verifications v WHERE v.claim_id = c.id)")
        sql = f"""
            SELECT c.id, c.statement, c.scope, c.claim_type, c.confidence,
                   v.id AS verification_id, v.verdict, v.confidence AS verification_confidence,
                   v.summary, v.method, v.agent, v.created_at AS verified_at
            FROM claims c
            LEFT JOIN claim_verifications v ON v.id = (
                SELECT v2.id FROM claim_verifications v2
                WHERE v2.claim_id = c.id
                ORDER BY v2.created_at DESC, v2.rowid DESC LIMIT 1
            )
            WHERE {" AND ".join(where)}
            ORDER BY c.confidence DESC, c.statement
        """
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        items: list[dict] = []
        for row in rows:
            item = {
                "id": row["id"],
                "statement": row["statement"],
                "scope": row["scope"],
                "claim_type": row["claim_type"],
                "confidence": row["confidence"],
            }
            if row["verification_id"]:
                item["verification"] = {
                    "id": row["verification_id"],
                    "verdict": row["verdict"],
                    "confidence": row["verification_confidence"],
                    "summary": row["summary"],
                    "method": row["method"],
                    "agent": row["agent"],
                    "verified_at": row["verified_at"],
                }
            else:
                item["verification"] = None
            items.append(item)
        return items

    def add_entity_alias(self, entity_id: str, alias: str) -> dict | None:
        alias = alias.strip()
        if not alias:
            raise ValueError("entity alias is required")
        with self.connect() as conn:
            entity = conn.execute("SELECT id, canonical_name FROM entities WHERE id = ?", (entity_id,)).fetchone()
            if entity is None:
                return None
            if alias.casefold() == entity["canonical_name"].casefold():
                raise ValueError("alias duplicates canonical name")
            existing = conn.execute(
                "SELECT entity_id FROM entity_aliases WHERE alias = ? COLLATE NOCASE", (alias,)
            ).fetchone()
            if existing is not None:
                if existing["entity_id"] == entity_id:
                    return {"entity_id": entity_id, "alias": alias}
                raise ValueError("alias belongs to another entity")
            created_at = self._now()
            conn.execute(
                "INSERT INTO entity_aliases(alias, entity_id, created_at) VALUES(?, ?, ?)",
                (alias, entity_id, created_at),
            )
            after = {"entity_id": entity_id, "alias": alias, "created_at": created_at}
            self._audit(
                conn,
                action="add_alias",
                object_kind="entity",
                object_id=entity_id,
                before={},
                after=after,
            )
            return after

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

    def document(self, path: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM documents WHERE path = ?", (path,)).fetchone()

    def document_by_id(self, document_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()

    def blocks_for_document(self, document_id: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM blocks WHERE document_id = ? ORDER BY ordinal",
                    (document_id,),
                )
            )

    def objects_for_document(self, document_id: str) -> list[dict]:
        """Snapshot sourced Entity/Concept identities before a document changes."""
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT m.object_id AS id, m.object_kind AS kind,
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
                   WHERE b.document_id = ?
                     AND m.object_kind IN ('entity', 'concept')
                   ORDER BY m.object_kind, m.object_id""",
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows if row["name"]]

    def set_document_status(self, document_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE documents SET status = ? WHERE id = ?", (status, document_id))

    def replace_view_dependencies(
        self,
        *,
        view_id: str,
        view_kind: str,
        input_hash: str,
        source_ids: set[str],
    ) -> None:
        """Replace the complete dependency snapshot for one materialized view."""
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM dependencies WHERE target_id = ? AND target_kind = ?",
                (view_id, view_kind),
            )
            conn.executemany(
                """INSERT INTO dependencies(source_id, target_id, target_kind, input_hash)
                   VALUES(?, ?, ?, ?)""",
                ((source_id, view_id, view_kind, input_hash) for source_id in sorted(source_ids)),
            )

    def view_dependencies(self, view_id: str, view_kind: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """SELECT source_id, target_id, target_kind, input_hash
                       FROM dependencies
                       WHERE target_id = ? AND target_kind = ?
                       ORDER BY source_id""",
                    (view_id, view_kind),
                )
            )

    def extraction_is_current(self, block_id: str, block_hash: str, prompt_version: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status FROM block_extractions WHERE block_id = ? AND block_hash = ? AND prompt_version = ?",
                (block_id, block_hash, prompt_version),
            ).fetchone()
            return row is not None and row["status"] == "complete"

    def claim_extraction_is_current(self, block_id: str, block_hash: str, prompt_version: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status FROM claim_extractions WHERE block_id = ? AND block_hash = ? AND prompt_version = ?",
                (block_id, block_hash, prompt_version),
            ).fetchone()
            return row is not None and row["status"] == "complete"

    def save_block_claim_extraction(
        self,
        *,
        block_id: str,
        block_hash: str,
        prompt_version: int,
        extracted_at: str,
        claims: list[dict],
    ) -> None:
        """Replace only one block's Claim/Evidence layer.

        Guard: when the source content is unchanged and this round produced no
        claims, the previous claims/evidence are preserved instead of being
        destroyed — a transient empty extraction must not wipe existing claims.
        """
        with self.connect() as conn:
            source_path, source_topic = self._block_source(conn, block_id)
            previous_row = conn.execute(
                "SELECT block_hash FROM claim_extractions WHERE block_id = ?", (block_id,)
            ).fetchone()
            content_changed = previous_row is None or previous_row["block_hash"] != block_hash
            keep_legacy = not claims and not content_changed
            if not keep_legacy:
                incoming_ids = [claim["id"] for claim in claims]
                previous_claims: dict[str, sqlite3.Row] = {}
                if incoming_ids:
                    placeholders = ",".join("?" * len(incoming_ids))
                    previous_claims = {
                        row["id"]: row
                        for row in conn.execute(
                            f"SELECT id, statement, user_edited FROM claims WHERE id IN ({placeholders})",
                            incoming_ids,
                        )
                    }
                evidence_statuses = {
                    row["id"]: row["status"]
                    for row in conn.execute("SELECT id, status FROM evidence WHERE block_id = ?", (block_id,))
                }
                conn.execute(
                    "DELETE FROM semantic_mentions WHERE block_id = ? AND object_kind = 'claim'",
                    (block_id,),
                )
                conn.execute("DELETE FROM evidence WHERE block_id = ?", (block_id,))
                for claim in claims:
                    conn.execute(
                        """
                        INSERT INTO claims(id, statement, scope, claim_type, confidence, status)
                        VALUES(:id, :statement, :scope, :claim_type, :confidence, 'active')
                        ON CONFLICT(id) DO UPDATE SET
                            statement=CASE WHEN user_edited = 1 THEN statement ELSE excluded.statement END,
                            scope=CASE WHEN user_edited = 1 THEN scope ELSE excluded.scope END,
                            claim_type=CASE WHEN user_edited = 1 THEN claim_type ELSE excluded.claim_type END,
                            confidence=max(confidence, excluded.confidence), status=status
                        """,
                        claim,
                    )
                    previous = previous_claims.get(claim["id"])
                    if previous is None:
                        self._record_change(
                            conn,
                            change_kind="added",
                            object_kind="claim",
                            object_id=claim["id"],
                            label=claim["statement"],
                            detail={"claim_type": claim["claim_type"], "scope": claim.get("scope", "")},
                            source_path=source_path,
                            topic=source_topic,
                        )
                    elif not previous["user_edited"] and previous["statement"] != claim["statement"]:
                        self._record_change(
                            conn,
                            change_kind="updated",
                            object_kind="claim",
                            object_id=claim["id"],
                            label=claim["statement"],
                            detail={"claim_type": claim["claim_type"], "previous_statement": previous["statement"]},
                            source_path=source_path,
                            topic=source_topic,
                        )
                    conn.execute(
                        "INSERT OR IGNORE INTO semantic_mentions(object_id, object_kind, block_id) VALUES(?, 'claim', ?)",
                        (claim["id"], block_id),
                    )
                    conn.execute(
                        """
                        INSERT INTO evidence(id, claim_id, block_id, quote_hash, status)
                        VALUES(:id, :claim_id, :block_id, :quote_hash, :status)
                        ON CONFLICT(id) DO NOTHING
                        """,
                        {
                            **claim["evidence"],
                            "status": evidence_statuses.get(claim["evidence"]["id"], "active"),
                        },
                    )
                self._invalidate_orphan_claims(
                    conn,
                    reason="replaced_by_recompile",
                    source_path=source_path,
                    topic=source_topic,
                )
            conn.execute(
                """
                INSERT INTO claim_extractions(block_id, block_hash, prompt_version, status, extracted_at, error)
                VALUES(?, ?, ?, 'complete', ?, NULL)
                ON CONFLICT(block_id) DO UPDATE SET
                    block_hash=excluded.block_hash,
                    prompt_version=excluded.prompt_version,
                    status='complete',
                    extracted_at=excluded.extracted_at,
                    error=NULL
                """,
                (block_id, block_hash, prompt_version, extracted_at),
            )
            self._trim_change_log(conn)

    def mark_claim_extraction_failed(
        self,
        block_id: str,
        block_hash: str,
        prompt_version: int,
        extracted_at: str,
        error: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO claim_extractions(block_id, block_hash, prompt_version, status, extracted_at, error)
                VALUES(?, ?, ?, 'failed', ?, ?)
                ON CONFLICT(block_id) DO UPDATE SET
                    block_hash=excluded.block_hash,
                    prompt_version=excluded.prompt_version,
                    status='failed',
                    extracted_at=excluded.extracted_at,
                    error=excluded.error
                """,
                (block_id, block_hash, prompt_version, extracted_at, error[:1000]),
            )

    def save_block_extraction(
        self,
        *,
        block_id: str,
        block_hash: str,
        prompt_version: int,
        extracted_at: str,
        concepts: list[dict],
        entities: list[dict],
        claims: list[dict],
    ) -> None:
        """Replace one block's semantic output in a single transaction.

        Guard: when the source content is unchanged and this round produced no
        claims, the previous claims/evidence are preserved instead of being
        destroyed — a transient empty extraction must not wipe existing claims.
        """
        with self.connect() as conn:
            source_path, source_topic = self._block_source(conn, block_id)
            # Extraction-time dedup: when a variant spelling (parenthetical
            # annotation, whitespace, case) matches an existing active object,
            # reuse that id so mentions/relations merge instead of duplicating.
            # The upsert below then refreshes description/confidence on the
            # existing row while keeping its canonical name.
            for obj, table in [(c, "concepts") for c in concepts] + [(e, "entities") for e in entities]:
                existing = conn.execute(
                    f"SELECT id FROM {table} WHERE name_fingerprint = ? AND status = 'active' AND id != ? LIMIT 1",
                    (name_fingerprint(obj["canonical_name"]), obj["id"]),
                ).fetchone()
                if existing is not None:
                    obj["id"] = existing["id"]
            concept_ids = [concept["id"] for concept in concepts]
            entity_ids = [entity["id"] for entity in entities]
            claim_ids = [claim["id"] for claim in claims]
            previous_extraction = conn.execute(
                "SELECT block_hash FROM block_extractions WHERE block_id = ?", (block_id,)
            ).fetchone()
            content_changed = previous_extraction is None or previous_extraction["block_hash"] != block_hash
            keep_legacy_claims = not claims and not content_changed
            existing_concepts = (
                {
                    row["id"]
                    for row in conn.execute(
                        f"SELECT id FROM concepts WHERE id IN ({','.join('?' * len(concept_ids))})", concept_ids
                    )
                }
                if concept_ids
                else set()
            )
            existing_entities = (
                {
                    row["id"]
                    for row in conn.execute(
                        f"SELECT id FROM entities WHERE id IN ({','.join('?' * len(entity_ids))})", entity_ids
                    )
                }
                if entity_ids
                else set()
            )
            previous_claims: dict[str, sqlite3.Row] = {}
            if claim_ids:
                previous_claims = {
                    row["id"]: row
                    for row in conn.execute(
                        f"SELECT id, statement, user_edited FROM claims WHERE id IN ({','.join('?' * len(claim_ids))})",
                        claim_ids,
                    )
                }
            evidence_statuses = {
                row["id"]: row["status"]
                for row in conn.execute("SELECT id, status FROM evidence WHERE block_id = ?", (block_id,))
            }
            conn.execute(
                "DELETE FROM semantic_mentions WHERE block_id = ? AND object_kind != 'claim'",
                (block_id,),
            ) if keep_legacy_claims else conn.execute("DELETE FROM semantic_mentions WHERE block_id = ?", (block_id,))
            conn.execute("DELETE FROM relations WHERE block_id = ?", (block_id,))
            if not keep_legacy_claims:
                conn.execute("DELETE FROM evidence WHERE block_id = ?", (block_id,))

            for concept in concepts:
                conn.execute(
                    """
                    INSERT INTO concepts(
                        id, canonical_name, description, confidence, status, name_fingerprint
                    )
                    VALUES(:id, :canonical_name, :description, :confidence, 'active', :name_fingerprint)
                    ON CONFLICT(id) DO UPDATE SET
                        description=CASE WHEN length(excluded.description) > length(description)
                            THEN excluded.description ELSE description END,
                        confidence=max(confidence, excluded.confidence), status='active'
                    """,
                    {**concept, "name_fingerprint": name_fingerprint(concept["canonical_name"])},
                )
                if concept["id"] not in existing_concepts:
                    self._record_change(
                        conn,
                        change_kind="added",
                        object_kind="concept",
                        object_id=concept["id"],
                        label=concept["canonical_name"],
                        source_path=source_path,
                        topic=source_topic,
                    )
                conn.execute(
                    "INSERT OR IGNORE INTO semantic_mentions(object_id, object_kind, block_id) VALUES(?, 'concept', ?)",
                    (concept["id"], block_id),
                )

            for entity in entities:
                conn.execute(
                    """
                    INSERT INTO entities(
                        id, canonical_name, entity_type, description, confidence, status, name_fingerprint
                    )
                    VALUES(
                        :id, :canonical_name, :entity_type, :description, :confidence, 'active', :name_fingerprint
                    )
                    ON CONFLICT(id) DO UPDATE SET
                        description=CASE WHEN length(excluded.description) > length(description)
                            THEN excluded.description ELSE description END,
                        confidence=max(confidence, excluded.confidence), status='active'
                    """,
                    {**entity, "name_fingerprint": name_fingerprint(entity["canonical_name"])},
                )
                if entity["id"] not in existing_entities:
                    self._record_change(
                        conn,
                        change_kind="added",
                        object_kind="entity",
                        object_id=entity["id"],
                        label=entity["canonical_name"],
                        detail={"entity_type": entity.get("entity_type", "")},
                        source_path=source_path,
                        topic=source_topic,
                    )
                conn.execute(
                    "INSERT OR IGNORE INTO semantic_mentions(object_id, object_kind, block_id) VALUES(?, 'entity', ?)",
                    (entity["id"], block_id),
                )

            # An Entity and a Concept extracted from the same source block have
            # a traceable, controlled association.  It is intentionally not a
            # stronger semantic assertion than RELATED_TO; that requires an
            # explicit relation extractor and evidence review.
            for entity in entities:
                for concept in concepts:
                    conn.execute(
                        """INSERT INTO relations(
                               id, source_id, relation_type, target_id, confidence, evidence_id, block_id
                           ) VALUES(?, ?, 'RELATED_TO', ?, ?, NULL, ?)
                           ON CONFLICT(id) DO UPDATE SET confidence=excluded.confidence,
                                                        block_id=excluded.block_id""",
                        (
                            stable_id("relation", block_id, entity["id"], "RELATED_TO", concept["id"]),
                            entity["id"],
                            concept["id"],
                            min(float(entity.get("confidence") or 0), float(concept.get("confidence") or 0)),
                            block_id,
                        ),
                    )

            for claim in claims:
                conn.execute(
                    """
                    INSERT INTO claims(id, statement, scope, claim_type, confidence, status)
                    VALUES(:id, :statement, :scope, :claim_type, :confidence, 'active')
                    ON CONFLICT(id) DO UPDATE SET
                        statement=CASE WHEN user_edited = 1 THEN statement ELSE excluded.statement END,
                        scope=CASE WHEN user_edited = 1 THEN scope ELSE excluded.scope END,
                        claim_type=CASE WHEN user_edited = 1 THEN claim_type ELSE excluded.claim_type END,
                        confidence=max(confidence, excluded.confidence), status=status
                    """,
                    claim,
                )
                previous = previous_claims.get(claim["id"])
                if previous is None:
                    self._record_change(
                        conn,
                        change_kind="added",
                        object_kind="claim",
                        object_id=claim["id"],
                        label=claim["statement"],
                        detail={"claim_type": claim["claim_type"], "scope": claim.get("scope", "")},
                        source_path=source_path,
                        topic=source_topic,
                    )
                elif not previous["user_edited"] and previous["statement"] != claim["statement"]:
                    self._record_change(
                        conn,
                        change_kind="updated",
                        object_kind="claim",
                        object_id=claim["id"],
                        label=claim["statement"],
                        detail={"claim_type": claim["claim_type"], "previous_statement": previous["statement"]},
                        source_path=source_path,
                        topic=source_topic,
                    )
                conn.execute(
                    "INSERT OR IGNORE INTO semantic_mentions(object_id, object_kind, block_id) VALUES(?, 'claim', ?)",
                    (claim["id"], block_id),
                )
                evidence = claim["evidence"]
                conn.execute(
                    """
                    INSERT INTO evidence(id, claim_id, block_id, quote_hash, status)
                    VALUES(:id, :claim_id, :block_id, :quote_hash, :status)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    {**evidence, "status": evidence_statuses.get(evidence["id"], "active")},
                )

            conn.execute(
                """
                INSERT INTO block_extractions(block_id, block_hash, prompt_version, status, extracted_at, error)
                VALUES(?, ?, ?, 'complete', ?, NULL)
                ON CONFLICT(block_id) DO UPDATE SET
                    block_hash=excluded.block_hash,
                    prompt_version=excluded.prompt_version,
                    status='complete',
                    extracted_at=excluded.extracted_at,
                    error=NULL
                """,
                (block_id, block_hash, prompt_version, extracted_at),
            )
            conn.execute(
                """
                INSERT INTO claim_extractions(block_id, block_hash, prompt_version, status, extracted_at, error)
                VALUES(?, ?, ?, 'complete', ?, NULL)
                ON CONFLICT(block_id) DO UPDATE SET
                    block_hash=excluded.block_hash,
                    prompt_version=excluded.prompt_version,
                    status='complete',
                    extracted_at=excluded.extracted_at,
                    error=NULL
                """,
                (block_id, block_hash, prompt_version, extracted_at),
            )
            self._invalidate_orphan_claims(
                conn,
                reason="replaced_by_recompile",
                source_path=source_path,
                topic=source_topic,
            ) if not keep_legacy_claims else None
            self._trim_change_log(conn)

    def mark_extraction_failed(
        self,
        block_id: str,
        block_hash: str,
        prompt_version: int,
        extracted_at: str,
        error: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO block_extractions(block_id, block_hash, prompt_version, status, extracted_at, error)
                VALUES(?, ?, ?, 'failed', ?, ?)
                ON CONFLICT(block_id) DO UPDATE SET
                    block_hash=excluded.block_hash,
                    prompt_version=excluded.prompt_version,
                    status='failed',
                    extracted_at=excluded.extracted_at,
                    error=excluded.error
                """,
                (block_id, block_hash, prompt_version, extracted_at, error[:1000]),
            )

    def replace_document(
        self,
        *,
        document: dict,
        blocks: list,
    ) -> None:
        """Atomically replace a parsed document and its block snapshot."""
        self.initialize()
        with self.connect() as conn:
            existed = conn.execute("SELECT 1 FROM documents WHERE id = ?", (document["id"],)).fetchone()
            conn.execute(
                """
                INSERT INTO documents(id, path, content_hash, title, topic, tags_json, status, compiled_at)
                VALUES(:id, :path, :content_hash, :title, :topic, :tags_json, :status, :compiled_at)
                ON CONFLICT(id) DO UPDATE SET
                    path=excluded.path,
                    content_hash=excluded.content_hash,
                    title=excluded.title,
                    topic=excluded.topic,
                    tags_json=excluded.tags_json,
                    status=excluded.status,
                    compiled_at=excluded.compiled_at
                """,
                document,
            )
            new_ids = {block.id for block in blocks}
            existing = {
                row["id"] for row in conn.execute("SELECT id FROM blocks WHERE document_id = ?", (document["id"],))
            }
            stale = existing - new_ids
            if stale:
                conn.executemany("DELETE FROM blocks WHERE id = ?", ((item,) for item in stale))
                self._invalidate_orphan_claims(
                    conn,
                    reason="source_block_removed",
                    source_path=document.get("path", ""),
                    topic=document.get("topic", ""),
                )
            self._record_change(
                conn,
                change_kind="updated" if existed else "added",
                object_kind="document",
                object_id=document["id"],
                label=document.get("title", ""),
                source_path=document.get("path", ""),
                topic=document.get("topic", ""),
            )
            self._trim_change_log(conn)
            conn.executemany(
                """
                INSERT INTO blocks(
                    id, document_id, block_type, heading_path_json, ordinal,
                    content, content_hash, start_line, end_line
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    ordinal=excluded.ordinal,
                    start_line=excluded.start_line,
                    end_line=excluded.end_line
                """,
                (
                    (
                        block.id,
                        document["id"],
                        block.block_type,
                        json.dumps(block.heading_path, ensure_ascii=False),
                        block.ordinal,
                        block.content,
                        block.content_hash,
                        block.start_line,
                        block.end_line,
                    )
                    for block in blocks
                ),
            )

    def purge_missing_documents(self, keep_paths: Sequence[str | Path] | None = None) -> list[str]:
        """Delete documents whose source is missing or outside the compile set.

        Args:
            keep_paths: 本次编译覆盖的笔记绝对路径集合。提供时，磁盘上存在但
                不在该集合内的记录（如隐藏目录中的文件）也会被清理；为 None 时
                仅清理磁盘上已不存在的记录。

        Returns:
            受影响的主题列表。
        """
        self.initialize()
        keep: set[str] | None = None
        if keep_paths is not None:
            keep = {str(Path(p).relative_to(self.workspace)) for p in keep_paths}
        with self.connect() as conn:
            rows = list(conn.execute("SELECT id, path, title, topic FROM documents"))
            missing = [
                row
                for row in rows
                if not (self.workspace / row["path"]).is_file()
                or (keep is not None and row["path"] not in keep)
            ]
            if not missing:
                return []
            conn.executemany("DELETE FROM documents WHERE id = ?", ((row["id"],) for row in missing))
            removed_paths = [row["path"] for row in missing]
            self._invalidate_orphan_claims(
                conn,
                reason="source_deleted",
                detail={"documents": removed_paths[:8]},
            )
            for row in missing:
                self._record_change(
                    conn,
                    change_kind="removed",
                    object_kind="document",
                    object_id=row["id"],
                    label=row["title"] or row["path"],
                    source_path=row["path"],
                    topic=row["topic"],
                )
            conn.execute(
                """DELETE FROM concepts
                   WHERE NOT EXISTS (
                       SELECT 1 FROM semantic_mentions
                       WHERE semantic_mentions.object_id = concepts.id
                         AND semantic_mentions.object_kind = 'concept'
                   )"""
            )
            conn.execute(
                """DELETE FROM entities
                   WHERE NOT EXISTS (
                       SELECT 1 FROM semantic_mentions
                       WHERE semantic_mentions.object_id = entities.id
                         AND semantic_mentions.object_kind = 'entity'
                   )"""
            )
            self._trim_change_log(conn)
            return sorted({row["topic"] for row in missing if row["topic"]})

    def deactivate_noise_objects(self) -> dict:
        """Deactivate stored objects whose names are deterministic noise.

        Covers legacy noise written before the extraction gate existed (file
        names like ``prepare.py``, flag tokens like ``--ar``, heading-number
        prefixes like ``06_四阶十二步法``, merged ``A/B`` names, domain names).
        Rows are kept with ``status='inactive'`` so audit history survives, but
        they stop appearing in workbench lists and aggregated pages.
        """
        from sidecar.semantic.extractor import _is_noise_object_name

        self.initialize()
        stats = {"entities": 0, "concepts": 0}
        with self.connect() as conn:
            for table, kind in (("entities", "entity"), ("concepts", "concept")):
                rows = list(conn.execute(f"SELECT id, canonical_name FROM {table} WHERE status = 'active'"))
                for row in rows:
                    if not _is_noise_object_name(row["canonical_name"]):
                        continue
                    conn.execute(f"UPDATE {table} SET status = 'inactive' WHERE id = ?", (row["id"],))
                    conn.execute(
                        "DELETE FROM semantic_mentions WHERE object_id = ? AND object_kind = ?",
                        (row["id"], kind),
                    )
                    conn.execute(
                        "DELETE FROM relations WHERE source_id = ? OR target_id = ?",
                        (row["id"], row["id"]),
                    )
                    self._record_change(
                        conn,
                        change_kind="deactivated",
                        object_kind=kind,
                        object_id=row["id"],
                        label=row["canonical_name"],
                        detail={"reason": "noise_object_name"},
                    )
                    stats["entities" if kind == "entity" else "concepts"] += 1
            self._trim_change_log(conn)
        return stats

    def purge_orphan_objects(
        self,
        *,
        min_confidence: float = 0.8,
        max_name_length: int = 20,
    ) -> dict:
        """清理孤立且平庸的实体/概念。

        条件：
        - 无 mentions（孤立）
        - 置信度 < min_confidence
        - 名称长度 <= max_name_length（短名称更可能是平庸的）
        - 名称不是专有名词（不含数字、不全是英文大写）

        返回清理统计。
        """
        import re

        self.initialize()
        stats = {"entities": 0, "concepts": 0}

        def _is_mundane_name(name: str) -> bool:
            """判断名称是否平庸（通用词、单个人名等）。"""
            # 全是英文大写（如 RAG、API）不是平庸的
            if name.isupper() and name.isalpha():
                return False
            # 包含数字（如 GPT-4、Python 3）不是平庸的
            if re.search(r"\d", name):
                return False
            # 包含连字符或下划线（如 LangChain-2）不是平庸的
            if "-" in name or "_" in name:
                return False
            # 长度超过阈值不是平庸的
            if len(name) > max_name_length:
                return False
            # 中文名称长度放宽
            if any("\u4e00" <= c <= "\u9fff" for c in name) and len(name) > max_name_length * 1.5:
                return False
            return True

        with self.connect() as conn:
            for table, kind in (("entities", "entity"), ("concepts", "concept")):
                # 查找孤立的对象
                rows = list(
                    conn.execute(
                        f"""SELECT id, canonical_name, confidence FROM {table}
                           WHERE status = 'active'
                             AND confidence < ?
                             AND id NOT IN (
                                 SELECT DISTINCT object_id FROM semantic_mentions
                                 WHERE object_kind = ?
                             )""",
                        (min_confidence, kind),
                    )
                )
                for row in rows:
                    if not _is_mundane_name(row["canonical_name"]):
                        continue
                    conn.execute(f"UPDATE {table} SET status = 'inactive' WHERE id = ?", (row["id"],))
                    conn.execute(
                        "DELETE FROM semantic_mentions WHERE object_id = ? AND object_kind = ?",
                        (row["id"], kind),
                    )
                    conn.execute(
                        "DELETE FROM relations WHERE source_id = ? OR target_id = ?",
                        (row["id"], row["id"]),
                    )
                    self._record_change(
                        conn,
                        change_kind="deactivated",
                        object_kind=kind,
                        object_id=row["id"],
                        label=row["canonical_name"],
                        detail={"reason": "orphan_mundane_object", "confidence": row["confidence"]},
                    )
                    stats["entities" if kind == "entity" else "concepts"] += 1
            self._trim_change_log(conn)
        return stats

    def merge_duplicate_entities(self) -> dict:
        """Merge same-object rows across entities AND concepts.

        Grouping key is the name fingerprint (case/whitespace/parenthetical-
        annotation insensitive), so variant spellings (``RAG`` vs
        ``RAG（检索增强生成）``) collapse into one row. The highest-confidence
        row is kept; mentions/relations are moved over, duplicates become
        inactive, and each merge is audited in the change log.

        Returns merge statistics per kind.
        """
        self.initialize()
        stats = {"merged_groups": 0, "merged_entities": 0, "merged_concepts": 0}

        with self.connect() as conn:
            for table, kind, group_key in (
                ("entities", "entity", "merged_entities"),
                ("concepts", "concept", "merged_concepts"),
            ):
                groups: dict[str, list[dict]] = {}
                for row in conn.execute(
                    f"""SELECT id, canonical_name, description, confidence
                        FROM {table} WHERE status = 'active'
                        ORDER BY confidence DESC"""
                ):
                    fp = name_fingerprint(row["canonical_name"])
                    groups.setdefault(fp, []).append(dict(row))

                for fp, group in groups.items():
                    if len(group) <= 1:
                        continue
                    keeper_id = group[0]["id"]
                    stats["merged_groups"] += 1
                    stats[group_key] += len(group) - 1

                    for dup in group[1:]:
                        dup_id = dup["id"]
                        # 转移 mentions（同 block 重复 mention 自动忽略，避免主键冲突）
                        conn.execute(
                            """INSERT OR IGNORE INTO semantic_mentions(object_id, object_kind, block_id)
                               SELECT ?, object_kind, block_id FROM semantic_mentions
                               WHERE object_id = ? AND object_kind = ?""",
                            (keeper_id, dup_id, kind),
                        )
                        conn.execute(
                            "DELETE FROM semantic_mentions WHERE object_id = ? AND object_kind = ?",
                            (dup_id, kind),
                        )
                        # 转移 relations（source）
                        conn.execute(
                            """UPDATE relations SET source_id = ?
                               WHERE source_id = ? AND target_id != ?""",
                            (keeper_id, dup_id, keeper_id),
                        )
                        # 转移 relations（target）
                        conn.execute(
                            """UPDATE relations SET target_id = ?
                               WHERE target_id = ? AND source_id != ?""",
                            (keeper_id, dup_id, keeper_id),
                        )
                        # 删除自引用关系
                        conn.execute(
                            "DELETE FROM relations WHERE source_id = ? AND target_id = ?",
                            (keeper_id, keeper_id),
                        )
                        # 标记为 inactive
                        conn.execute(
                            f"UPDATE {table} SET status = 'inactive' WHERE id = ?",
                            (dup_id,),
                        )
                        self._record_change(
                            conn,
                            change_kind="merged",
                            object_kind=kind,
                            object_id=dup_id,
                            label=dup["canonical_name"],
                            detail={"merged_into": keeper_id, "reason": "duplicate_name"},
                        )

            self._trim_change_log(conn)
        return stats

    def deactivate_orphan_objects(self) -> dict:
        """Deactivate objects with zero source mentions.

        Zero-mention objects carry no traceable evidence (their mentions were
        removed with source blocks, or they were never linked). They bloat the
        aggregated pages while adding no verifiable value, so they are
        deactivated regardless of confidence. Idempotent.
        """
        self.initialize()
        stats = {"entities": 0, "concepts": 0}
        with self.connect() as conn:
            for table, kind in (("entities", "entity"), ("concepts", "concept")):
                rows = list(
                    conn.execute(
                        f"""SELECT id, canonical_name FROM {table}
                           WHERE status = 'active'
                             AND NOT EXISTS (
                                 SELECT 1 FROM semantic_mentions
                                 WHERE object_id = {table}.id AND object_kind = ?
                             )""",
                        (kind,),
                    )
                )
                for row in rows:
                    conn.execute(f"UPDATE {table} SET status = 'inactive' WHERE id = ?", (row["id"],))
                    conn.execute(
                        "DELETE FROM relations WHERE source_id = ? OR target_id = ?",
                        (row["id"], row["id"]),
                    )
                    self._record_change(
                        conn,
                        change_kind="deactivated",
                        object_kind=kind,
                        object_id=row["id"],
                        label=row["canonical_name"],
                        detail={"reason": "orphan_no_mentions"},
                    )
                    stats["entities" if kind == "entity" else "concepts"] += 1
            self._trim_change_log(conn)
        return stats

    def delete_inactive_objects(self) -> dict:
        """Permanently delete inactive entity/concept rows.

        Deactivated objects are normally kept for audit; this method removes
        them outright after their mentions/relations have already been dropped.
        The deactivation events already exist in the change log, so no per-row
        audit is appended here. Returns per-kind deletion counts.
        """
        self.initialize()
        stats = {"entities": 0, "concepts": 0}
        with self.connect() as conn:
            for table, kind in (("entities", "entity"), ("concepts", "concept")):
                rows = list(conn.execute(f"SELECT id FROM {table} WHERE status = 'inactive'"))
                for row in rows:
                    conn.execute(f"DELETE FROM {table} WHERE id = ?", (row["id"],))
                    conn.execute(
                        "DELETE FROM relations WHERE source_id = ? OR target_id = ?",
                        (row["id"], row["id"]),
                    )
                    stats["entities" if kind == "entity" else "concepts"] += 1
        return stats

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
