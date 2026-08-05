"""Transactional SQLite storage for semantic compiler state.

``SemanticStore`` is a facade: it composes four per-table-family stores
(documents/objects/claims/audit) sharing one connection-management base
(:class:`~sidecar.semantic.store_base.SemanticStoreBase`) and delegates every
public method unchanged, so external callers keep the original API surface.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

from sidecar.semantic.store_audit import AUDIT_SCHEMA, AuditStore
from sidecar.semantic.store_base import (
    CHANGE_LOG_LIMIT,
    CLAIM_POLICY_VERSION,
    CORE_SCHEMA,
    FINGERPRINT_ALGORITHM_VERSION,
    SCHEMA_VERSION,
    SemanticStoreBase,
)
from sidecar.semantic.store_claims import CLAIMS_SCHEMA, ClaimsStore
from sidecar.semantic.store_documents import DOCUMENTS_SCHEMA, DocumentsStore
from sidecar.semantic.store_objects import OBJECTS_SCHEMA, ObjectsStore, name_fingerprint

__all__ = [
    "CHANGE_LOG_LIMIT",
    "CLAIM_POLICY_VERSION",
    "FINGERPRINT_ALGORITHM_VERSION",
    "SCHEMA_VERSION",
    "SemanticStore",
    "name_fingerprint",
]

# 全量 schema：基类基础设施表 + 四个表族 DDL，保持 CREATE IF NOT EXISTS 幂等。
_SCHEMA = CORE_SCHEMA + DOCUMENTS_SCHEMA + OBJECTS_SCHEMA + CLAIMS_SCHEMA + AUDIT_SCHEMA


class SemanticStore(SemanticStoreBase):
    """门面类：组合四个表族子存储，公开 API 与原单体实现完全一致。"""

    def __init__(self, workspace: str | Path):
        super().__init__(workspace)
        self.documents = DocumentsStore(self)
        self.objects = ObjectsStore(self)
        self.claims = ClaimsStore(self)
        self.audit = AuditStore(self)

    def initialize(self) -> None:
        """统一编排各表族迁移，执行顺序与原单体实现一致。"""
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            # Set the journal mode only during explicit schema initialization.
            # Repeating this PRAGMA on every read connection can contend with an
            # active compiler transaction and make otherwise read-only RPCs wait.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA)
            self.claims.migrate_columns(conn)
            self.objects.migrate(conn)
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self.claims.migrate_policy(conn)

    # ------------------------------------------------------------------
    # documents / blocks / block_extractions / dependencies
    # ------------------------------------------------------------------

    def document(self, path: str) -> sqlite3.Row | None:
        return self.documents.document(path)

    def document_by_id(self, document_id: str) -> sqlite3.Row | None:
        return self.documents.document_by_id(document_id)

    def blocks_for_document(self, document_id: str) -> list[sqlite3.Row]:
        return self.documents.blocks_for_document(document_id)

    def set_document_status(self, document_id: str, status: str) -> None:
        self.documents.set_document_status(document_id, status)

    def replace_view_dependencies(
        self,
        *,
        view_id: str,
        view_kind: str,
        input_hash: str,
        source_ids: set[str],
    ) -> None:
        self.documents.replace_view_dependencies(
            view_id=view_id,
            view_kind=view_kind,
            input_hash=input_hash,
            source_ids=source_ids,
        )

    def view_dependencies(self, view_id: str, view_kind: str) -> list[sqlite3.Row]:
        return self.documents.view_dependencies(view_id, view_kind)

    def extraction_is_current(self, block_id: str, block_hash: str, prompt_version: int) -> bool:
        return self.documents.extraction_is_current(block_id, block_hash, prompt_version)

    def mark_extraction_failed(
        self,
        block_id: str,
        block_hash: str,
        prompt_version: int,
        extracted_at: str,
        error: str,
    ) -> None:
        self.documents.mark_extraction_failed(block_id, block_hash, prompt_version, extracted_at, error)

    def replace_document(
        self,
        *,
        document: dict,
        blocks: list,
    ) -> None:
        self.documents.replace_document(document=document, blocks=blocks)

    def purge_missing_documents(self, keep_paths: Sequence[str | Path] | None = None) -> list[str]:
        return self.documents.purge_missing_documents(keep_paths)

    # ------------------------------------------------------------------
    # entities / concepts / aliases / relations（含合并治理）
    # ------------------------------------------------------------------

    def objects_for_document(self, document_id: str) -> list[dict]:
        return self.objects.objects_for_document(document_id)

    def add_entity_alias(self, entity_id: str, alias: str) -> dict | None:
        return self.objects.add_entity_alias(entity_id, alias)

    def rebuild_document_relations(self, document_ids: set[str]) -> None:
        self.objects.rebuild_document_relations(document_ids)

    def deactivate_noise_objects(self) -> dict:
        return self.objects.deactivate_noise_objects()

    def purge_orphan_objects(
        self,
        *,
        min_confidence: float = 0.8,
        max_name_length: int = 20,
    ) -> dict:
        return self.objects.purge_orphan_objects(
            min_confidence=min_confidence,
            max_name_length=max_name_length,
        )

    def merge_duplicate_entities(self) -> dict:
        return self.objects.merge_duplicate_entities()

    def deactivate_orphan_objects(self) -> dict:
        return self.objects.deactivate_orphan_objects()

    def delete_inactive_objects(self) -> dict:
        return self.objects.delete_inactive_objects()

    # ------------------------------------------------------------------
    # claims / evidence / claim_extractions / claim_verifications
    # ------------------------------------------------------------------

    def update_claim(
        self,
        claim_id: str,
        *,
        statement: str,
        scope: str,
        claim_type: str,
    ) -> dict | None:
        return self.claims.update_claim(claim_id, statement=statement, scope=scope, claim_type=claim_type)

    def set_claim_status(self, claim_id: str, status: str) -> dict | None:
        return self.claims.set_claim_status(claim_id, status)

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
        return self.claims.save_claim_verification(
            claim_id,
            verdict=verdict,
            confidence=confidence,
            summary=summary,
            method=method,
            agent=agent,
            sources=sources,
        )

    def set_evidence_status(self, evidence_id: str, status: str) -> dict | None:
        return self.claims.set_evidence_status(evidence_id, status)

    def claim_verifications(self, claim_id: str, *, limit: int = 10) -> list[dict]:
        return self.claims.claim_verifications(claim_id, limit=limit)

    def latest_claim_verification(self, claim_id: str) -> dict | None:
        return self.claims.latest_claim_verification(claim_id)

    def list_claims_for_verification(
        self,
        *,
        topic: str | None = None,
        limit: int | None = None,
        verified: bool | None = None,
    ) -> list[dict]:
        return self.claims.list_claims_for_verification(topic=topic, limit=limit, verified=verified)

    def claim_extraction_is_current(self, block_id: str, block_hash: str, prompt_version: int) -> bool:
        return self.claims.claim_extraction_is_current(block_id, block_hash, prompt_version)

    def save_block_claim_extraction(
        self,
        *,
        block_id: str,
        block_hash: str,
        prompt_version: int,
        extracted_at: str,
        claims: list[dict],
    ) -> None:
        self.claims.save_block_claim_extraction(
            block_id=block_id,
            block_hash=block_hash,
            prompt_version=prompt_version,
            extracted_at=extracted_at,
            claims=claims,
        )

    def mark_claim_extraction_failed(
        self,
        block_id: str,
        block_hash: str,
        prompt_version: int,
        extracted_at: str,
        error: str,
    ) -> None:
        self.claims.mark_claim_extraction_failed(block_id, block_hash, prompt_version, extracted_at, error)

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
        self.claims.save_block_extraction(
            block_id=block_id,
            block_hash=block_hash,
            prompt_version=prompt_version,
            extracted_at=extracted_at,
            concepts=concepts,
            entities=entities,
            claims=claims,
        )

    # ------------------------------------------------------------------
    # 变更审计查询
    # ------------------------------------------------------------------

    def change_counts(self, *, days: int = 7) -> list[dict]:
        return self.audit.change_counts(days=days)

    def recent_changes(
        self,
        *,
        days: int = 7,
        limit: int = 100,
        offset: int = 0,
        object_kind: str | None = None,
    ) -> tuple[list[dict], int]:
        return self.audit.recent_changes(days=days, limit=limit, offset=offset, object_kind=object_kind)

    def topics_with_changes(self, *, days: int = 7, limit: int = 50) -> list[str]:
        return self.audit.topics_with_changes(days=days, limit=limit)

    def topic_changes(
        self,
        *,
        topic: str,
        days: int = 7,
        limit: int = 60,
    ) -> list[dict]:
        return self.audit.topic_changes(topic=topic, days=days, limit=limit)
