"""Entities/concepts/aliases persistence and merge governance (semantic store family)."""

from __future__ import annotations

import re
import sqlite3

from sidecar.semantic.ids import stable_id
from sidecar.semantic.store_base import FINGERPRINT_ALGORITHM_VERSION, SemanticStoreBase

OBJECTS_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS entity_aliases (
    alias TEXT PRIMARY KEY COLLATE NOCASE,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);
"""

_PAREN_PAIR_RE = re.compile(r"[（(][^（()）]*[)）]")


def _stem_english_suffix(word: str) -> str:
    """轻量英文复数归一，仅供查重指纹使用，不做完整词干还原。

    覆盖 Skill/Skills、Token/Tokens、Model/Models、Query/Queries、Box/Boxes
    等常规复数形态；对 ss/us/is/os/as 结尾的词（class/status/analysis/chaos/
    alias）保守跳过，避免误并专有名词。
    """
    if len(word) <= 3 or not word.isascii() or not word.isalpha():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is", "os", "as")):
        return word[:-1]
    return word


def name_fingerprint(name: str) -> str:
    """Normalize an object name for duplicate detection at extraction time.

    Strips parenthetical annotations (``RAG（检索增强生成）`` → ``RAG``), all
    whitespace and case, and stems English plural suffixes (``Skills`` →
    ``Skill``), so variant spellings of the same object resolve to the same
    fingerprint and merge into one row instead of duplicating.
    """
    text = _PAREN_PAIR_RE.sub("", name)
    tokens = [_stem_english_suffix(token) for token in text.casefold().split()]
    fp = "".join(tokens)
    return fp or "".join(text.casefold().split())


class ObjectsStore(SemanticStoreBase):
    """entities / concepts / aliases / relations / mentions 表族与合并治理。"""

    schema_sql = OBJECTS_SCHEMA

    def __init__(self, facade: SemanticStoreBase):
        super().__init__(facade.workspace)
        self._facade = facade

    def initialize(self) -> None:
        self._facade.initialize()

    def migrate(self, conn: sqlite3.Connection) -> None:
        """对象表族迁移：relations.block_id、名称指纹列与存量指纹回填。"""
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
        # 指纹算法升级（如英文复数词干化）后全量重算存量指纹，使
        # Skill/Skills 这类历史变体也能被后续 merge_duplicate_entities 合并。
        fingerprint_row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'fingerprint_algorithm_version'"
        ).fetchone()
        if fingerprint_row is None or fingerprint_row["value"] != str(FINGERPRINT_ALGORITHM_VERSION):
            for table in ("entities", "concepts"):
                rows = conn.execute(f"SELECT id, canonical_name FROM {table}").fetchall()
                for row in rows:
                    conn.execute(
                        f"UPDATE {table} SET name_fingerprint = ? WHERE id = ?",
                        (name_fingerprint(row["canonical_name"]), row["id"]),
                    )
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('fingerprint_algorithm_version', ?)",
                (str(FINGERPRINT_ALGORITHM_VERSION),),
            )
        for table in ("entities", "concepts"):
            rows = conn.execute(f"SELECT id, canonical_name FROM {table} WHERE name_fingerprint IS NULL").fetchall()
            for row in rows:
                conn.execute(
                    f"UPDATE {table} SET name_fingerprint = ? WHERE id = ?",
                    (name_fingerprint(row["canonical_name"]), row["id"]),
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

    def rebuild_document_relations(self, document_ids: set[str]) -> None:
        """重建受影响文档的对象共现关系（同块 + 跨块，频次加权）。

        同块共现：任意对象组合（实体↔实体、概念↔概念、实体↔概念）建
        RELATED_TO 边，置信度 = min(两端对象置信度)——实体↔概念的组合已由
        save_block_extraction 在块级创建，这里补齐其余组合。

        跨块共现：同一文档内 ≥2 个不同块共同提及同一对象对时，按共现块数
        频次加权置信度（每块 +0.08，上限 +0.25），替换该文档内该对的自动
        块级边（evidence_id IS NULL），低于 0.4 的弱共现不建边。

        仅处理自动边：手工边（带 evidence_id 或 merge 来源）不受影响。
        """
        if not document_ids:
            return
        placeholders = ",".join("?" for _ in document_ids)
        ids = tuple(sorted(document_ids))
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT m.object_kind AS kind, m.object_id AS id, b.document_id AS doc,
                           b.id AS block_id
                    FROM semantic_mentions m
                    JOIN blocks b ON b.id = m.block_id
                    WHERE b.document_id IN ({placeholders})
                      AND m.object_kind IN ('entity', 'concept')
                      AND (EXISTS (SELECT 1 FROM entities e WHERE e.id = m.object_id AND e.status = 'active')
                           OR EXISTS (SELECT 1 FROM concepts c WHERE c.id = m.object_id AND c.status = 'active'))""",
                ids,
            ).fetchall()
        if not rows:
            return
        conf: dict[tuple[str, str], float] = {}
        with self.connect() as conn:
            for row in conn.execute("SELECT id, COALESCE(confidence, 0.0) AS c FROM entities WHERE status = 'active'"):
                conf[("entity", row["id"])] = float(row["c"])
            for row in conn.execute("SELECT id, COALESCE(confidence, 0.0) AS c FROM concepts WHERE status = 'active'"):
                conf[("concept", row["id"])] = float(row["c"])
        # 按文档分组：对象 -> 出现的块集合。
        docs: dict[str, dict[tuple[str, str], set[str]]] = {}
        for row in rows:
            docs.setdefault(row["doc"], {}).setdefault((row["kind"], row["id"]), set()).add(row["block_id"])
        with self.connect() as conn:
            for doc_id, objects in docs.items():
                keys = sorted(objects)
                for i, key_a in enumerate(keys):
                    for key_b in keys[i + 1 :]:
                        common = objects[key_a] & objects[key_b]
                        if not common:
                            continue
                        base = min(conf.get(key_a, 0.0), conf.get(key_b, 0.0))
                        source, target = sorted((key_a, key_b))
                        if len(common) >= 2:
                            # 跨块共现：频次加权，替换该文档内该对的自动块级边。
                            weighted = min(0.99, base + 0.08 * len(common))
                            if weighted < 0.4:
                                continue
                            conn.execute(
                                """DELETE FROM relations
                                   WHERE ((source_id = ? AND target_id = ?) OR (source_id = ? AND target_id = ?))
                                     AND evidence_id IS NULL
                                     AND block_id IN (SELECT id FROM blocks WHERE document_id = ?)""",
                                (source[1], target[1], target[1], source[1], doc_id),
                            )
                            conn.execute(
                                """INSERT INTO relations(
                                       id, source_id, relation_type, target_id, confidence, evidence_id, block_id
                                   ) VALUES(?, ?, 'RELATED_TO', ?, ?, NULL, NULL)
                                   ON CONFLICT(id) DO UPDATE SET
                                       confidence=excluded.confidence""",
                                (
                                    stable_id("relation", "cooccur", doc_id, source[1], "RELATED_TO", target[1]),
                                    source[1],
                                    target[1],
                                    round(weighted, 3),
                                ),
                            )
                        else:
                            # 同块共现：仅同一块出现，补齐非 entity↔concept 组合。
                            if {key_a[0], key_b[0]} == {"entity", "concept"}:
                                continue  # 已由 save_block_extraction 创建
                            block_id = next(iter(common))
                            conn.execute(
                                """INSERT INTO relations(
                                       id, source_id, relation_type, target_id, confidence, evidence_id, block_id
                                   ) VALUES(?, ?, 'RELATED_TO', ?, ?, NULL, ?)
                                   ON CONFLICT(id) DO UPDATE SET confidence=excluded.confidence,
                                                                block_id=excluded.block_id""",
                                (
                                    stable_id("relation", block_id, source[1], "RELATED_TO", target[1]),
                                    source[1],
                                    target[1],
                                    round(base, 3),
                                    block_id,
                                ),
                            )

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
