"""Transactional SQLite storage for semantic compiler state."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from config.settings import WORKSPACE_APP_FOLDER

SCHEMA_VERSION = 2
CLAIM_POLICY_VERSION = 3

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
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    quote_hash TEXT NOT NULL,
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
    evidence_id TEXT REFERENCES evidence(id) ON DELETE SET NULL
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
"""


class SemanticStore:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.root = self.workspace / WORKSPACE_APP_FOLDER / "compiler"
        self.path = self.root / "semantic.db"

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(_SCHEMA)
            claim_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(claims)")
            }
            if "claim_type" not in claim_columns:
                conn.execute(
                    "ALTER TABLE claims ADD COLUMN claim_type TEXT NOT NULL DEFAULT 'conclusion' "
                    "CHECK(claim_type IN ('conclusion', 'hypothesis'))"
                )
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'claim_policy_version'"
            ).fetchone()
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
                conn.execute(
                    "UPDATE documents SET status = 'parsed' WHERE status IN ('semantic', 'partial')"
                )
                conn.execute(
                    "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('claim_policy_version', ?)",
                    (str(CLAIM_POLICY_VERSION),),
                )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
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

    def set_document_status(self, document_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE documents SET status = ? WHERE id = ?", (status, document_id))

    def extraction_is_current(self, block_id: str, block_hash: str, prompt_version: int) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status FROM block_extractions WHERE block_id = ? AND block_hash = ? AND prompt_version = ?",
                (block_id, block_hash, prompt_version),
            ).fetchone()
            return row is not None and row["status"] == "complete"

    def claim_extraction_is_current(
        self, block_id: str, block_hash: str, prompt_version: int
    ) -> bool:
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
        """Replace only one block's Claim/Evidence layer."""
        with self.connect() as conn:
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
                        statement=excluded.statement,
                        scope=excluded.scope,
                        claim_type=excluded.claim_type,
                        confidence=max(confidence, excluded.confidence), status='active'
                    """,
                    claim,
                )
                conn.execute(
                    "INSERT OR IGNORE INTO semantic_mentions(object_id, object_kind, block_id) VALUES(?, 'claim', ?)",
                    (claim["id"], block_id),
                )
                conn.execute(
                    """
                    INSERT INTO evidence(id, claim_id, block_id, quote_hash)
                    VALUES(:id, :claim_id, :block_id, :quote_hash)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    claim["evidence"],
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
            conn.execute(
                """DELETE FROM claims
                   WHERE NOT EXISTS (SELECT 1 FROM evidence WHERE evidence.claim_id = claims.id)"""
            )

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
        """Replace one block's semantic output in a single transaction."""
        with self.connect() as conn:
            conn.execute("DELETE FROM semantic_mentions WHERE block_id = ?", (block_id,))
            conn.execute("DELETE FROM evidence WHERE block_id = ?", (block_id,))

            for concept in concepts:
                conn.execute(
                    """
                    INSERT INTO concepts(id, canonical_name, description, confidence, status)
                    VALUES(:id, :canonical_name, :description, :confidence, 'active')
                    ON CONFLICT(id) DO UPDATE SET
                        description=CASE WHEN length(excluded.description) > length(description)
                            THEN excluded.description ELSE description END,
                        confidence=max(confidence, excluded.confidence), status='active'
                    """,
                    concept,
                )
                conn.execute(
                    "INSERT OR IGNORE INTO semantic_mentions(object_id, object_kind, block_id) VALUES(?, 'concept', ?)",
                    (concept["id"], block_id),
                )

            for entity in entities:
                conn.execute(
                    """
                    INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)
                    VALUES(:id, :canonical_name, :entity_type, :description, :confidence, 'active')
                    ON CONFLICT(id) DO UPDATE SET
                        description=CASE WHEN length(excluded.description) > length(description)
                            THEN excluded.description ELSE description END,
                        confidence=max(confidence, excluded.confidence), status='active'
                    """,
                    entity,
                )
                conn.execute(
                    "INSERT OR IGNORE INTO semantic_mentions(object_id, object_kind, block_id) VALUES(?, 'entity', ?)",
                    (entity["id"], block_id),
                )

            for claim in claims:
                conn.execute(
                    """
                    INSERT INTO claims(id, statement, scope, claim_type, confidence, status)
                    VALUES(:id, :statement, :scope, :claim_type, :confidence, 'active')
                    ON CONFLICT(id) DO UPDATE SET
                        statement=excluded.statement,
                        scope=excluded.scope,
                        claim_type=excluded.claim_type,
                        confidence=max(confidence, excluded.confidence), status='active'
                    """,
                    claim,
                )
                conn.execute(
                    "INSERT OR IGNORE INTO semantic_mentions(object_id, object_kind, block_id) VALUES(?, 'claim', ?)",
                    (claim["id"], block_id),
                )
                evidence = claim["evidence"]
                conn.execute(
                    """
                    INSERT INTO evidence(id, claim_id, block_id, quote_hash)
                    VALUES(:id, :claim_id, :block_id, :quote_hash)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    evidence,
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
            conn.execute(
                """DELETE FROM claims
                   WHERE NOT EXISTS (SELECT 1 FROM evidence WHERE evidence.claim_id = claims.id)"""
            )

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
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM blocks WHERE document_id = ?", (document["id"],)
                )
            }
            stale = existing - new_ids
            if stale:
                conn.executemany("DELETE FROM blocks WHERE id = ?", ((item,) for item in stale))
                conn.execute(
                    """DELETE FROM claims
                       WHERE NOT EXISTS (SELECT 1 FROM evidence WHERE evidence.claim_id = claims.id)"""
                )
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

    def purge_missing_documents(self) -> list[str]:
        """Delete missing source snapshots and return their affected topics."""
        self.initialize()
        with self.connect() as conn:
            rows = list(conn.execute("SELECT id, path, topic FROM documents"))
            missing = [row for row in rows if not (self.workspace / row["path"]).is_file()]
            if not missing:
                return []
            conn.executemany("DELETE FROM documents WHERE id = ?", ((row["id"],) for row in missing))
            conn.execute(
                """DELETE FROM claims
                   WHERE NOT EXISTS (SELECT 1 FROM evidence WHERE evidence.claim_id = claims.id)"""
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
            return sorted({row["topic"] for row in missing if row["topic"]})
