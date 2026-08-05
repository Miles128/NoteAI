"""Documents/blocks/block_extractions persistence (semantic store family)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from sidecar.semantic.store_base import SemanticStoreBase

DOCUMENTS_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS block_extractions (
    block_id TEXT PRIMARY KEY REFERENCES blocks(id) ON DELETE CASCADE,
    block_hash TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    error TEXT
);
"""


class DocumentsStore(SemanticStoreBase):
    """documents / blocks / block_extractions / dependencies 表族的读写。"""

    schema_sql = DOCUMENTS_SCHEMA

    def __init__(self, facade: SemanticStoreBase):
        super().__init__(facade.workspace)
        # 门面负责编排全部表族的迁移；子模块的 initialize 一律转发给门面，
        # 保持与单体 SemanticStore.initialize() 完全一致的语义。
        self._facade = facade

    def initialize(self) -> None:
        self._facade.initialize()

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

    def save_block_extraction(self, **kwargs) -> None:
        """薄委托：写入主体在 claims/objects 侧（见 ``ClaimsStore.save_block_extraction``）。"""
        self._facade.save_block_extraction(**kwargs)  # type: ignore[attr-defined]

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
                if not (self.workspace / row["path"]).is_file() or (keep is not None and row["path"] not in keep)
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
