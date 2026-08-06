"""Claims/evidence/verifications persistence (semantic store family)."""

from __future__ import annotations

import json
import sqlite3

from sidecar.semantic.ids import stable_id
from sidecar.semantic.store_base import CLAIM_POLICY_VERSION, SemanticStoreBase
from sidecar.semantic.store_objects import name_fingerprint

CLAIMS_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS claim_extractions (
    block_id TEXT PRIMARY KEY REFERENCES blocks(id) ON DELETE CASCADE,
    block_hash TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    error TEXT
);
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


class ClaimsStore(SemanticStoreBase):
    """claims / evidence / claim_extractions / claim_verifications 表族。"""

    schema_sql = CLAIMS_SCHEMA

    def __init__(self, facade: SemanticStoreBase):
        super().__init__(facade.workspace)
        self._facade = facade

    def initialize(self) -> None:
        self._facade.initialize()

    def migrate_columns(self, conn: sqlite3.Connection) -> None:
        """claims/evidence 表的增量列迁移。"""
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

    def migrate_policy(self, conn: sqlite3.Connection) -> None:
        """Claim 策略版本升级：作废全部存量 claim/evidence 派生数据。"""
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

        写入主体横跨 objects/claims 两个表族，但 claims/evidence 的替换、孤儿
        claim 失效与 claim_extractions 记账是本方法的核心语义，故整体实现归于
        claims 侧（documents 侧保留薄委托）；全部写入在同一连接事务内完成。

        Guard: when the source content is unchanged and this round produced no
        claims, the previous claims/evidence are preserved instead of being
        destroyed — a transient empty extraction must not wipe existing claims.
        """
        with self.connect() as conn:
            source_path, source_topic = self._block_source(conn, block_id)
            # Extraction-time dedup: when a variant spelling (parenthetical
            # annotation, whitespace, case, punctuation) matches an existing
            # active object, reuse that id so mentions/relations merge instead
            # of duplicating. The upsert below then refreshes
            # description/confidence on the existing row while keeping its
            # canonical name. The differing spelling is preserved as an alias
            # (entity_aliases / concept_aliases) so the alternate name of the
            # same object survives.
            #
            # Cross-kind dedup: a concept whose fingerprint matches an active
            # entity (or vice versa) is re-assigned to the pre-existing kind
            # and reuses its id — the earlier object wins, so the same name
            # never lives in both tables at once. The moved object keeps the
            # existing row's kind-specific fields (upsert never overwrites
            # canonical_name / entity_type) and its name is recorded as an
            # alias of the surviving row.
            for obj, table, alias_table, alias_column in [
                (c, "concepts", "concept_aliases", "concept_id") for c in concepts
            ] + [(e, "entities", "entity_aliases", "entity_id") for e in entities]:
                existing = conn.execute(
                    f"SELECT id, canonical_name FROM {table} WHERE name_fingerprint = ? AND status = 'active' AND id != ? LIMIT 1",
                    (name_fingerprint(obj["canonical_name"]), obj["id"]),
                ).fetchone()
                if existing is None:
                    other_table = "entities" if table == "concepts" else "concepts"
                    existing = conn.execute(
                        f"SELECT id, canonical_name FROM {other_table} WHERE name_fingerprint = ? AND status = 'active' LIMIT 1",
                        (name_fingerprint(obj["canonical_name"]),),
                    ).fetchone()
                    if existing is not None:
                        if table == "concepts":
                            concepts[:] = [c for c in concepts if c is not obj]
                            entities.append(obj)
                            obj["entity_type"] = obj.get("entity_type", "")
                            alias_table, alias_column = "entity_aliases", "entity_id"
                        else:
                            entities[:] = [e for e in entities if e is not obj]
                            concepts.append(obj)
                            alias_table, alias_column = "concept_aliases", "concept_id"
                if existing is not None:
                    obj["id"] = existing["id"]
                    if obj["canonical_name"].casefold() != existing["canonical_name"].casefold():
                        conn.execute(
                            f"INSERT OR IGNORE INTO {alias_table}(alias, {alias_column}, created_at) VALUES(?, ?, ?)",
                            (obj["canonical_name"], existing["id"], self._now()),
                        )
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
