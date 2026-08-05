"""Semantic workbench queries, explicit review actions and claim verification."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from sidecar import job_status
from sidecar.handlers.base import BaseHandler
from sidecar.handlers.cli_agent_handler import CliAgentHandler
from sidecar.semantic.ids import stable_id
from sidecar.semantic.store import SemanticStore


class SemanticHandler(BaseHandler):
    _TABS = {"overview", "claims", "concepts", "entities", "quality", "conflicts", "links"}
    _COMPILE_JOB_ID = "semantic-full-compile"
    # Workbench display intensity → minimum confidence for claims/objects.
    # "deep" keeps every item (including legacy rows without confidence).
    _INTENSITY_MIN_CONFIDENCE = {"light": 0.8, "standard": 0.5, "deep": 0.0}

    def _store(self) -> SemanticStore | None:
        workspace = self.config.workspace_path
        if not workspace:
            return None
        store = SemanticStore(workspace)
        # A workbench query must not take a schema/write lock while an ingest
        # compilation owns the database. New workspaces still get an empty
        # initialized store; existing stores are opened read-first.
        if not store.path.exists():
            store.initialize()
        return store

    @staticmethod
    def _page(params: dict) -> tuple[int, int]:
        try:
            limit = max(1, min(int(params.get("limit", 50)), 100))
            offset = max(0, int(params.get("offset", 0)))
        except (TypeError, ValueError):
            return 50, 0
        return limit, offset

    def _get_workbench(self, params):
        tab = str(params.get("tab", "overview") or "overview")
        if tab not in self._TABS:
            return {"success": False, "message": "未知语义视图"}
        intensity = str(params.get("intensity", "standard") or "standard")
        min_confidence = self._INTENSITY_MIN_CONFIDENCE.get(intensity)
        if min_confidence is None:
            min_confidence = self._INTENSITY_MIN_CONFIDENCE["standard"]
        store = self._store()
        if store is None:
            return {"success": False, "message": "未设置工作区"}
        if not store.path.exists():
            if tab == "overview":
                return self._overview(store)
            return {"success": True, "tab": tab, "items": [], "total": 0, "overview": self._empty_overview()}

        if tab == "overview":
            return self._overview(store)
        if tab == "links":
            return self._links(params)
        if tab == "conflicts":
            return self._conflicts(store, params)
        if tab == "quality":
            return self._quality(store, params)
        return self._semantic_list(store, tab, params, min_confidence=min_confidence)

    @staticmethod
    def _empty_overview() -> dict:
        return {
            "documents": 0,
            "blocks": 0,
            "concepts": 0,
            "entities": 0,
            "claims": 0,
            "evidence": 0,
            "deleted_claims": 0,
            "excluded_evidence": 0,
            "conflicts": 0,
            "updated_at": None,
            "source_documents": 0,
            "complete_documents": 0,
            "partial_documents": 0,
            "pending_documents": 0,
            "uncompiled_documents": 0,
        }

    def _overview(self, store: SemanticStore):
        source_documents = len(self._all_note_paths())
        if not store.path.exists():
            overview = self._empty_overview()
            overview["source_documents"] = source_documents
            overview["uncompiled_documents"] = source_documents
            return {
                "success": True,
                "tab": "overview",
                "overview": overview,
                "compile_job": job_status.get_job(self._COMPILE_JOB_ID),
                "items": [],
                "total": 0,
            }
        tables = ("documents", "blocks", "concepts", "entities", "claims", "evidence")
        with store.connect() as conn:
            overview = {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables}
            overview["claims"] = conn.execute(
                """SELECT count(*) FROM claims c WHERE c.status = 'active'
                   AND EXISTS (SELECT 1 FROM evidence e WHERE e.claim_id = c.id AND e.status = 'active')"""
            ).fetchone()[0]
            overview["evidence"] = conn.execute("SELECT count(*) FROM evidence WHERE status = 'active'").fetchone()[0]
            overview["deleted_claims"] = conn.execute(
                "SELECT count(*) FROM claims WHERE status = 'deleted'"
            ).fetchone()[0]
            overview["excluded_evidence"] = conn.execute(
                "SELECT count(*) FROM evidence WHERE status = 'excluded'"
            ).fetchone()[0]
            overview["conflicts"] = conn.execute(
                "SELECT count(*) FROM review_queue WHERE item_kind = 'claim_conflict' AND status = 'pending'"
            ).fetchone()[0]
            row = conn.execute("SELECT max(compiled_at) AS updated_at FROM documents").fetchone()
            overview["updated_at"] = row["updated_at"] if row else None
            statuses = {
                row["status"]: row["count"]
                for row in conn.execute("SELECT status, count(*) AS count FROM documents GROUP BY status")
            }
        overview["source_documents"] = source_documents
        overview["complete_documents"] = statuses.get("semantic", 0)
        overview["partial_documents"] = statuses.get("partial", 0)
        overview["pending_documents"] = statuses.get("pending_extraction", 0) + statuses.get("parsed", 0)
        overview["uncompiled_documents"] = max(0, source_documents - overview["documents"])
        return {
            "success": True,
            "tab": "overview",
            "overview": overview,
            "compile_job": job_status.get_job(self._COMPILE_JOB_ID),
            "items": [],
            "total": 0,
        }

    def _get_changes(self, params):
        """Read-only knowledge change digest; never triggers LLM or writes."""
        store = self._store()
        if store is None:
            return {"success": False, "message": "未设置工作区"}
        try:
            days = max(1, min(int(params.get("days", 7) or 7), 90))
        except (TypeError, ValueError):
            days = 7
        object_kind = str(params.get("object_kind") or "").strip() or None
        if object_kind not in {None, "claim", "entity", "concept", "document"}:
            return {"success": False, "message": "未知对象类型"}
        if not store.path.exists():
            return {"success": True, "days": days, "counts": [], "items": [], "total": 0}
        limit, offset = self._page(params)
        try:
            counts = store.change_counts(days=days)
            items, total = store.recent_changes(days=days, limit=limit, offset=offset, object_kind=object_kind)
        except sqlite3.OperationalError:
            # A stale or partially initialized store must never break the
            # read-only digest; surface an empty result instead of an error.
            return {"success": True, "days": days, "counts": [], "items": [], "total": 0}
        return {"success": True, "days": days, "counts": counts, "items": items, "total": total}

    def _get_topic_brief(self, params):
        """One-topic review brief from the change log.

        Uses the LLM when configured; otherwise falls back to a structured
        Markdown change list. Read-only — never writes to the store.
        """
        store = self._store()
        if store is None:
            return {"success": False, "message": "未设置工作区"}
        try:
            days = max(1, min(int(params.get("days", 7) or 7), 90))
        except (TypeError, ValueError):
            days = 7
        topic = str(params.get("topic") or "").strip()
        if not store.path.exists():
            return {"success": True, "days": days, "topics": [], "topic": "", "brief": "", "fallback": False}
        topics = store.topics_with_changes(days=days)
        if not topic:
            return {"success": True, "days": days, "topics": topics[:50], "topic": "", "brief": "", "fallback": False}
        changes = store.topic_changes(topic=topic, days=days)
        if not changes:
            brief = f"## 主题简报：{topic}\n\n过去 {days} 天该主题没有语义变化。"
            return {
                "success": True,
                "days": days,
                "topics": topics[:50],
                "topic": topic,
                "brief": brief,
                "fallback": False,
            }
        records = "\n".join(
            f"- [{c['created_at'][:10]}] {c['change_kind']} · {c['object_kind']}: {c['label'] or c['object_id']}"
            + (f"（来源：{Path(c['source_path']).name}）" if c.get("source_path") else "")
            for c in changes
        )
        brief, fallback = self._compose_topic_brief(topic, days, records)
        return {
            "success": True,
            "days": days,
            "topics": topics[:50],
            "topic": topic,
            "brief": brief,
            "fallback": fallback,
        }

    @staticmethod
    def _compose_topic_brief(topic: str, days: int, records: str) -> tuple[str, bool]:
        """LLM-generated brief when available; structured fallback otherwise."""
        from prompts import TOPIC_BRIEF_PROMPT
        from utils.llm_utils import call_llm_raw

        try:
            prompt = TOPIC_BRIEF_PROMPT.format(topic_name=topic, days=days, change_records=records)
            text = call_llm_raw(prompt, temperature=0.3)
        except Exception:
            text = ""
        if not text or not text.strip():
            fallback = (
                f"## 主题简报：{topic}\n\n"
                f"（未配置 LLM 或生成失败，以下为结构化变化记录）\n\n"
                f"过去 {days} 天变化：\n\n{records}\n"
            )
            return fallback, True
        return text.strip(), False

    def _all_note_paths(self) -> list[Path]:
        workspace = self.config.workspace_path
        if not workspace:
            return []
        notes = Path(workspace) / "Notes"
        if not notes.is_dir():
            return []
        return sorted(
            path
            for path in notes.rglob("*.md")
            if not path.name.startswith(".")
            and not path.name.endswith("_综述.md")
            and not any(part.startswith(".") for part in path.relative_to(notes).parts)
        )

    def _start_full_compile(self, _params):
        return self._start_semantic_compile(_params, claims_only=False)

    def _start_claims_compile(self, _params):
        """只重抽命题/证据，不触碰实体/概念。

        历史遗留场景：早期严格校验导致 claims 被整体清空，而 block_extractions
        已记录为 complete，常规全量编译会跳过这些块；本入口走 claim_extractions
        表，可只花一次 LLM 调用重抽全部命题。
        """
        return self._start_semantic_compile(_params, claims_only=True)

    def _start_semantic_compile(self, _params, *, claims_only: bool):
        workspace, err = self._require_workspace()
        if err:
            return err
        paths = self._all_note_paths()
        started = self._start_task(
            self._COMPILE_JOB_ID,
            self._run_full_compile,
            args=(workspace, paths),
            kwargs={"claims_only": claims_only},
            kind="semantic_compile",
            label="全库命题编译" if claims_only else "全库语义编译",
        )
        if not started:
            return {
                "success": True,
                "status": "running",
                "message": "全库语义编译正在进行",
                "job": job_status.get_job(self._COMPILE_JOB_ID),
            }
        return {
            "success": True,
            "status": "started",
            "total_documents": len(paths),
            "job": job_status.get_job(self._COMPILE_JOB_ID),
        }

    def _run_full_compile(self, workspace: str, paths: list[Path], *, claims_only: bool = False) -> None:
        from sidecar.semantic.compiler import compile_semantic_batch
        from sidecar.semantic.object_wiki import materialize_object_collection
        from sidecar.semantic.topic_state import materialize_topic_state
        from sidecar.semantic.wiki import materialize_topic_wiki_page

        total = max(len(paths), 1)
        store = SemanticStore(workspace)
        removed_topics = set(store.purge_missing_documents())

        def progress(current, _total, message):
            self._send_job_update(
                self._COMPILE_JOB_ID,
                progress=current / total,
                message=message,
                metadata={"processed_documents": current, "total_documents": len(paths)},
            )

        stats = compile_semantic_batch(workspace, paths, progress_cb=progress, claims_only=claims_only)
        cleanup_failures = []
        if not claims_only:
            for kind in ("entity", "concept"):
                try:
                    materialize_object_collection(store, kind)
                except (OSError, ValueError, sqlite3.Error) as exc:
                    cleanup_failures.append({"kind": f"{kind}_collection", "error": str(exc)})
        for topic in sorted(removed_topics):
            try:
                materialize_topic_state(store, topic)
                materialize_topic_wiki_page(store, topic)
            except (OSError, ValueError, sqlite3.Error) as exc:
                cleanup_failures.append({"kind": "removed_topic", "topic": topic, "error": str(exc)})
        if cleanup_failures:
            stats["failures"].extend({"cleanup": item} for item in cleanup_failures)
        materialized = stats.get("materialized", {})
        if claims_only:
            message = (
                f"全库命题编译完成：{stats['documents']} 篇，"
                f"命题 {stats['claims']} 条（拒绝 {stats['rejected_claims']}），失败块 {stats['failed_blocks']}"
            )
        else:
            materialized_message = (
                f"；已自动更新实体聚合页（涉及 {materialized.get('entities', 0)} 条）、"
                f"概念聚合页（涉及 {materialized.get('concepts', 0)} 条）、"
                f"主题页 {materialized.get('topics', 0)}"
            )
            message = (
                f"全库语义编译完成：{stats['documents']} 篇，失败块 {stats['failed_blocks']}{materialized_message}"
            )
        self._send_job_update(
            self._COMPILE_JOB_ID,
            progress=1,
            status="complete",
            message=message,
            metadata={
                "processed_documents": stats["documents"],
                "total_documents": len(paths),
                "blocks": stats["blocks"],
                "claims": stats["claims"],
                "rejected_claims": stats["rejected_claims"],
                "failed_blocks": stats["failed_blocks"],
                "pending_documents": stats["pending_documents"],
                "failure_count": len(stats["failures"]),
                "removed_topics": sorted(removed_topics),
                "materialized": materialized,
            },
        )

    def _get_compile_status(self, _params):
        return {
            "success": True,
            "job": job_status.get_job(self._COMPILE_JOB_ID),
            "total_documents": len(self._all_note_paths()),
        }

    def _semantic_list(self, store: SemanticStore, tab: str, params: dict, min_confidence: float | None = None):
        limit, offset = self._page(params)
        query = str(params.get("query", "") or "").strip()
        like = f"%{query}%"
        with store.connect() as conn:
            if tab == "claims":
                status = str(params.get("status", "active") or "active")
                if status not in {"active", "deleted", "all"}:
                    status = "active"
                status_clause = "" if status == "all" else "c.status = ? AND "
                args = (() if status == "all" else (status,)) + (query, like, like)
                evidence_clause = (
                    "AND (c.status = 'deleted' OR EXISTS "
                    "(SELECT 1 FROM evidence ae WHERE ae.claim_id = c.id AND ae.status = 'active'))"
                )
                where = f"WHERE {status_clause}(? = '' OR c.statement LIKE ? OR c.scope LIKE ?) {evidence_clause}"
                if min_confidence:
                    where += " AND c.confidence >= ?"
                    args = args + (min_confidence,)
                total = conn.execute(f"SELECT count(*) FROM claims c {where}", args).fetchone()[0]
                rows = conn.execute(
                    f"""SELECT c.id, c.statement, c.scope, c.claim_type, c.confidence, c.status,
                               sum(CASE WHEN e.status = 'active' THEN 1 ELSE 0 END) AS evidence_count,
                               sum(CASE WHEN e.status = 'excluded' THEN 1 ELSE 0 END) AS excluded_evidence_count,
                               v.verdict AS verification_verdict,
                               v.confidence AS verification_confidence,
                               v.method AS verification_method,
                               v.agent AS verification_agent,
                               v.created_at AS verified_at
                        FROM claims c LEFT JOIN evidence e ON e.claim_id = c.id
                        LEFT JOIN claim_verifications v ON v.id = (
                            SELECT v2.id FROM claim_verifications v2
                            WHERE v2.claim_id = c.id
                            ORDER BY v2.created_at DESC, v2.rowid DESC LIMIT 1
                        )
                        {where} GROUP BY c.id ORDER BY c.confidence DESC, c.statement LIMIT ? OFFSET ?""",
                    (*args, limit, offset),
                ).fetchall()
                items = []
                for row in rows:
                    item = dict(row)
                    verdict = item.pop("verification_verdict", None)
                    if verdict:
                        item["verification"] = {
                            "verdict": verdict,
                            "confidence": item.pop("verification_confidence"),
                            "method": item.pop("verification_method"),
                            "agent": item.pop("verification_agent"),
                            "verified_at": item.pop("verified_at"),
                        }
                    else:
                        item.pop("verification_confidence", None)
                        item.pop("verification_method", None)
                        item.pop("verification_agent", None)
                        item.pop("verified_at", None)
                        item["verification"] = None
                    evidence = conn.execute(
                        """SELECT e.id, e.status, d.path, d.title, d.topic, b.id AS block_id,
                                  b.heading_path_json, b.content, b.start_line, b.end_line
                           FROM evidence e JOIN blocks b ON b.id = e.block_id
                           JOIN documents d ON d.id = b.document_id
                           WHERE e.claim_id = ? ORDER BY d.path, b.ordinal""",
                        (row["id"],),
                    ).fetchall()
                    item["evidence"] = [self._evidence_row(value) for value in evidence]
                    items.append(item)
            else:
                table = tab
                kind = "concept" if tab == "concepts" else "entity"
                type_select = ", o.entity_type" if tab == "entities" else ""
                description_column = "o.description"
                where = "WHERE o.status = 'active' AND (? = '' OR o.canonical_name LIKE ? OR o.description LIKE ?)"
                args = (query, like, like)
                if min_confidence:
                    where += " AND o.confidence >= ?"
                    args = args + (min_confidence,)
                total = conn.execute(f"SELECT count(*) FROM {table} o {where}", args).fetchone()[0]
                rows = conn.execute(
                    f"""SELECT o.id, o.canonical_name, {description_column}, o.confidence{type_select},
                               count(m.block_id) AS mention_count,
                               count(DISTINCT b.document_id) AS source_count
                        FROM {table} o
                        LEFT JOIN semantic_mentions m ON m.object_id = o.id AND m.object_kind = ?
                        LEFT JOIN blocks b ON b.id = m.block_id
                        {where} GROUP BY o.id
                        ORDER BY mention_count DESC, o.canonical_name LIMIT ? OFFSET ?""",
                    (kind, *args, limit, offset),
                ).fetchall()
                items = [dict(row) for row in rows]
        return {"success": True, "tab": tab, "items": items, "total": total, "limit": limit, "offset": offset}

    @staticmethod
    def _evidence_row(row) -> dict:
        item = dict(row)
        try:
            item["heading_path"] = json.loads(item.pop("heading_path_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["heading_path"] = []
        item["excerpt"] = " ".join((item.pop("content", "") or "").split())[:220]
        return item

    def _get_detail(self, params):
        kind = str(params.get("kind", "") or "")
        object_id = str(params.get("id", "") or "")
        if kind not in {"concept", "entity", "claim"} or not object_id:
            return {"success": False, "message": "参数不完整"}
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        with store.connect() as conn:
            if kind == "claim":
                row = conn.execute(
                    "SELECT id, statement, scope, claim_type, confidence, status FROM claims WHERE id = ?",
                    (object_id,),
                ).fetchone()
                if row is None:
                    return {"success": False, "message": "命题不存在"}
                item = dict(row)
                rows = conn.execute(
                    """SELECT e.id, e.status, d.path, d.title, d.topic, b.id AS block_id,
                              b.heading_path_json, b.content, b.start_line, b.end_line
                       FROM evidence e JOIN blocks b ON b.id = e.block_id
                       JOIN documents d ON d.id = b.document_id
                       WHERE e.claim_id = ? ORDER BY d.path, b.ordinal""",
                    (object_id,),
                ).fetchall()
            else:
                table = "concepts" if kind == "concept" else "entities"
                row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (object_id,)).fetchone()
                if row is None:
                    return {"success": False, "message": "语义对象不存在"}
                item = dict(row)
                rows = conn.execute(
                    """SELECT d.path, d.title, d.topic, b.id AS block_id,
                              b.heading_path_json, b.content, b.start_line, b.end_line
                       FROM semantic_mentions m JOIN blocks b ON b.id = m.block_id
                       JOIN documents d ON d.id = b.document_id
                       WHERE m.object_id = ? AND m.object_kind = ?
                       ORDER BY d.path, b.ordinal""",
                    (object_id, kind),
                ).fetchall()
                if kind == "entity":
                    item["aliases"] = [
                        value["alias"]
                        for value in conn.execute(
                            "SELECT alias FROM entity_aliases WHERE entity_id = ? ORDER BY alias COLLATE NOCASE",
                            (object_id,),
                        )
                    ]
                related_rows = conn.execute(
                    """SELECT r.id, r.relation_type, r.confidence, r.source_id, r.target_id,
                              r.block_id
                       FROM relations r WHERE r.source_id = ? OR r.target_id = ?
                       ORDER BY r.relation_type, r.id""",
                    (object_id, object_id),
                ).fetchall()
                related = []
                for relation in related_rows:
                    other_id = relation["target_id"] if relation["source_id"] == object_id else relation["source_id"]
                    other = conn.execute(
                        "SELECT canonical_name, 'entity' AS kind FROM entities WHERE id = ? AND status = 'active' "
                        "UNION ALL SELECT canonical_name, 'concept' AS kind FROM concepts WHERE id = ? AND status = 'active'",
                        (other_id, other_id),
                    ).fetchone()
                    if other:
                        related.append(
                            {
                                "id": relation["id"],
                                "relation_type": relation["relation_type"],
                                "confidence": relation["confidence"],
                                "block_id": relation["block_id"],
                                "object_id": other_id,
                                "object_name": other["canonical_name"],
                                "object_kind": other["kind"],
                            }
                        )
                item["related"] = related
            audit_rows = conn.execute(
                """SELECT id, action, before_json, after_json, created_at
                   FROM semantic_audit_log WHERE object_kind = ? AND object_id = ?
                   ORDER BY created_at DESC LIMIT 20""",
                (kind, object_id),
            ).fetchall()
        item["sources"] = [self._evidence_row(value) for value in rows]
        item["verifications"] = store.claim_verifications(object_id) if kind == "claim" else []
        item["audit"] = [
            {
                "id": value["id"],
                "action": value["action"],
                "before": json.loads(value["before_json"] or "{}"),
                "after": json.loads(value["after_json"] or "{}"),
                "created_at": value["created_at"],
            }
            for value in audit_rows
        ]
        return {"success": True, "kind": kind, "item": item}

    def _verify_claim(self, params):
        """联网深度研究核查单个命题（CLI agent 模式），结果落库供工作台展示。

        CLI 深度研究可能耗时数分钟；与 CLI Agent 对话共用同一执行通道，
        因此复用 CliAgentHandler 的全局锁避免并发执行。
        """
        claim_id = str(params.get("id", "") or "")
        agent_id = str(params.get("agent", "") or "")
        if not claim_id or not agent_id:
            return {"success": False, "message": "参数不完整"}
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        claims = store.list_claims_for_verification(limit=5000)
        claim = next((item for item in claims if item["id"] == claim_id), None)
        if claim is None:
            return {"success": False, "message": "命题不存在或不可核查（仅支持 active 且有证据的命题）"}
        if not CliAgentHandler._cli_agent_lock.acquire(blocking=False):
            return {"success": False, "message": "CLI agent 正在运行其他任务，请稍后再试"}
        try:
            from sidecar.semantic.claim_verifier import verify_claim_via_cli

            result = verify_claim_via_cli(store, claim, agent_id=agent_id)
            if result.get("success"):
                # 只保留原始输出尾部，避免超大 RPC 响应
                result["output"] = (result.get("output") or "")[-2000:]
            return result
        finally:
            CliAgentHandler._cli_agent_lock.release()

    def _get_note_semantic_context(self, params):
        path = str(params.get("path", "") or "").replace("\\", "/")
        store = self._store()
        if not path or store is None or not store.path.exists():
            return {"success": True, "entities": [], "concepts": [], "claims": [], "relations": []}
        with store.connect() as conn:
            doc = conn.execute("SELECT id FROM documents WHERE path = ?", (path,)).fetchone()
            if doc is None:
                return {"success": True, "entities": [], "concepts": [], "claims": [], "relations": []}

            def objects(table, kind):
                return [
                    dict(row)
                    for row in conn.execute(
                        f"""SELECT DISTINCT o.id, o.canonical_name, o.description FROM {table} o
                        JOIN semantic_mentions m ON m.object_id = o.id AND m.object_kind = ?
                        JOIN blocks b ON b.id = m.block_id WHERE b.document_id = ? AND o.status = 'active'
                        ORDER BY o.canonical_name""",
                        (kind, doc["id"]),
                    )
                ]

            claims = [
                dict(row)
                for row in conn.execute(
                    """SELECT DISTINCT c.id, c.statement, c.claim_type FROM claims c JOIN evidence e ON e.claim_id = c.id
                   JOIN blocks b ON b.id = e.block_id WHERE b.document_id = ? AND c.status = 'active' AND e.status = 'active'
                   ORDER BY c.statement""",
                    (doc["id"],),
                )
            ]
            entities = objects("entities", "entity")
            concepts = objects("concepts", "concept")
            labels = {item["id"]: item["canonical_name"] for item in [*entities, *concepts]}
            relations = []
            for row in conn.execute(
                """SELECT DISTINCT r.id, r.source_id, r.target_id, r.relation_type, r.confidence
                   FROM relations r JOIN blocks b ON b.id = r.block_id
                   WHERE b.document_id = ? ORDER BY r.relation_type, r.id""",
                (doc["id"],),
            ):
                if row["source_id"] in labels and row["target_id"] in labels:
                    relations.append(
                        {**dict(row), "source_name": labels[row["source_id"]], "target_name": labels[row["target_id"]]}
                    )
        return {"success": True, "entities": entities, "concepts": concepts, "claims": claims, "relations": relations}

    def _update_claim(self, params):
        claim_id = str(params.get("id", "") or "")
        if not claim_id:
            return {"success": False, "message": "命题 ID 不能为空"}
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        try:
            item = store.update_claim(
                claim_id,
                statement=str(params.get("statement", "") or ""),
                scope=str(params.get("scope", "") or ""),
                claim_type=str(params.get("claim_type", "") or ""),
            )
        except ValueError as exc:
            return {"success": False, "message": str(exc)}
        return {"success": item is not None, "item": item, "message": "命题不存在" if item is None else ""}

    def _set_claim_status(self, params):
        claim_id = str(params.get("id", "") or "")
        status = str(params.get("status", "") or "")
        store = self._store()
        if not claim_id or store is None or not store.path.exists():
            return {"success": False, "message": "参数不完整或语义数据库不存在"}
        try:
            item = store.set_claim_status(claim_id, status)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}
        return {"success": item is not None, "item": item}

    def _set_evidence_status(self, params):
        evidence_id = str(params.get("id", "") or "")
        status = str(params.get("status", "") or "")
        store = self._store()
        if not evidence_id or store is None or not store.path.exists():
            return {"success": False, "message": "参数不完整或语义数据库不存在"}
        try:
            item = store.set_evidence_status(evidence_id, status)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}
        return {"success": item is not None, "item": item}

    def _add_entity_alias(self, params):
        entity_id = str(params.get("id", "") or "")
        alias = str(params.get("alias", "") or "")
        store = self._store()
        if not entity_id or store is None or not store.path.exists():
            return {"success": False, "message": "参数不完整或语义数据库不存在"}
        try:
            item = store.add_entity_alias(entity_id, alias)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}
        return {"success": item is not None, "item": item}

    def _get_topic_wiki_page(self, params):
        topic = str(params.get("topic", "") or "").strip()
        store = self._store()
        if not topic or store is None:
            return {"success": False, "message": "主题不能为空或未设置工作区"}
        from sidecar.semantic.wiki import build_topic_wiki_page

        page = build_topic_wiki_page(store, topic)
        return {
            "success": True,
            "topic": topic,
            "content": page["content"],
            "blocked_claim_ids": page["blocked_claim_ids"],
            "target": str(page["target"].relative_to(store.workspace)),
        }

    def _get_object_wiki_page(self, params):
        kind, object_id = str(params.get("kind", "")), str(params.get("id", ""))
        store = self._store()
        if kind not in {"entity", "concept"} or not object_id or store is None:
            return {"success": False, "message": "参数不完整"}
        from sidecar.semantic.object_wiki import build_object_page

        try:
            page = build_object_page(store, kind, object_id)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}
        return {"success": True, "content": page["content"], "target": str(page["target"].relative_to(store.workspace))}

    def _publish_object_wiki_page(self, params):
        kind, object_id = str(params.get("kind", "")), str(params.get("id", ""))
        store = self._store()
        if kind not in {"entity", "concept"} or not object_id or store is None:
            return {"success": False, "message": "参数不完整"}
        from sidecar.semantic.object_wiki import materialize_object_collection

        try:
            target = materialize_object_collection(store, kind)
        except (OSError, ValueError) as exc:
            return {"success": False, "message": str(exc)}
        return {
            "success": True,
            "path": str(target.relative_to(store.workspace)),
            "aggregate": True,
        }

    def _publish_topic_wiki_page(self, params):
        topic = str(params.get("topic", "") or "").strip()
        store = self._store()
        if not topic or store is None:
            return {"success": False, "message": "主题不能为空或未设置工作区"}
        from sidecar.semantic.wiki import materialize_topic_wiki_page

        try:
            target = materialize_topic_wiki_page(store, topic)
        except OSError as exc:
            return {"success": False, "message": f"语义页发布失败：{exc}"}
        try:
            from sidecar.wiki_utils import sync_semantic_links

            wiki_links = sync_semantic_links()
        except Exception:
            wiki_links = None
        return {
            "success": True,
            "topic": topic,
            "path": str(target.relative_to(store.workspace)),
            "wiki_links": wiki_links,
        }

    def _conflicts(self, store: SemanticStore, params: dict):
        limit, offset = self._page(params)
        status = str(params.get("status", "pending") or "pending")
        if status not in {"pending", "reviewed", "all"}:
            status = "pending"
        where = "item_kind = 'claim_conflict'"
        args: list[object] = []
        if status != "all":
            where += " AND status = ?"
            args.append(status)
        with store.connect() as conn:
            total = conn.execute(f"SELECT count(*) FROM review_queue WHERE {where}", args).fetchone()[0]
            rows = conn.execute(
                f"""SELECT id, payload_json, reason, status, created_at FROM review_queue
                    WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (*args, limit, offset),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.pop("payload_json") or "{}")
            except json.JSONDecodeError:
                item["payload"] = {}
            items.append(item)
        return {
            "success": True,
            "tab": "conflicts",
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "status": status,
        }

    def _review_conflict(self, params):
        item_id = str(params.get("id", "") or "")
        status = str(params.get("status", "reviewed") or "reviewed")
        if not item_id or status not in {"pending", "reviewed"}:
            return {"success": False, "message": "参数不完整"}
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        with store.connect() as conn:
            cursor = conn.execute(
                "UPDATE review_queue SET status = ? WHERE id = ? AND item_kind = 'claim_conflict'",
                (status, item_id),
            )
        return {"success": cursor.rowcount > 0, "id": item_id, "status": status}

    def _scan_conflicts(self, params):
        """手动触发结构化冲突检测：重扫 claims 快照并落库（幂等）。"""
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        from sidecar.semantic.conflict_detector import scan_and_persist

        return scan_and_persist(store)

    @staticmethod
    def _quality_key(*parts: str) -> str:
        payload = "\0".join(parts).encode("utf-8")
        return "entity-quality-" + hashlib.sha256(payload).hexdigest()[:20]

    @staticmethod
    def _normalized_entity_name(value: str) -> str:
        return "".join(str(value or "").casefold().split())

    def _quality_issues(self, store: SemanticStore) -> list[dict]:
        """Derive entity-quality issues from the current SQLite snapshot only."""
        with store.connect() as conn:
            entities = [
                dict(row)
                for row in conn.execute(
                    "SELECT id, canonical_name, entity_type, description, confidence FROM entities WHERE status = 'active'"
                )
            ]
            mentions = {
                row["entity_id"]: int(row["count"])
                for row in conn.execute(
                    """SELECT object_id AS entity_id, count(*) AS count FROM semantic_mentions
                       WHERE object_kind = 'entity' GROUP BY object_id"""
                )
            }
            linked = {
                row["entity_id"]
                for row in conn.execute(
                    """SELECT source_id AS entity_id FROM relations
                       UNION SELECT target_id AS entity_id FROM relations"""
                )
            }
            aliases = [dict(row) for row in conn.execute("SELECT alias, entity_id FROM entity_aliases")]
            concept_ids = {
                row["id"]
                for row in conn.execute("SELECT id FROM concepts WHERE status = 'active'")
            }
            relation_endpoint_ids = {
                row["entity_id"]
                for row in conn.execute(
                    "SELECT source_id AS entity_id FROM relations UNION SELECT target_id AS entity_id FROM relations"
                )
            }
            reviewed = {
                row["id"]: json.loads(row["payload_json"] or "{}")
                for row in conn.execute(
                    "SELECT id, payload_json FROM review_queue WHERE item_kind = 'entity_quality' AND status = 'reviewed'"
                )
            }

        by_id = {entity["id"]: entity for entity in entities}
        canonical_groups: dict[str, list[str]] = {}
        alias_groups: dict[str, list[str]] = {}
        # Relations legitimately link entities to concepts (RELATED_TO co-occurrence),
        # so concept endpoints must count as known. Only truly missing endpoints are dangling.
        dangling_relations = relation_endpoint_ids - set(by_id) - concept_ids
        for entity in entities:
            canonical_groups.setdefault(self._normalized_entity_name(entity["canonical_name"]), []).append(entity["id"])
        for alias in aliases:
            alias_groups.setdefault(self._normalized_entity_name(alias["alias"]), []).append(alias["entity_id"])

        issues: list[dict] = []

        def add(rule: str, entity: dict, reason: str, candidates: list[str] | None = None) -> None:
            candidate_ids = sorted(set(candidates or []))
            issue_id = self._quality_key(rule, entity["id"], *candidate_ids)
            fingerprint = self._quality_key(
                rule,
                entity["id"],
                entity["canonical_name"],
                str(entity["confidence"]),
                str(mentions.get(entity["id"], 0)),
                *candidate_ids,
            )
            persisted = reviewed.get(issue_id, {})
            status = "reviewed" if persisted.get("fingerprint") == fingerprint else "pending"
            issues.append(
                {
                    "id": issue_id,
                    "rule": rule,
                    "entity_id": entity["id"],
                    "entity_name": entity["canonical_name"],
                    "entity_type": entity["entity_type"],
                    "confidence": entity["confidence"],
                    "mention_count": mentions.get(entity["id"], 0),
                    "reason": reason,
                    "candidate_ids": candidate_ids,
                    "candidate_names": [by_id[value]["canonical_name"] for value in candidate_ids if value in by_id],
                    "fingerprint": fingerprint,
                    "status": status,
                }
            )

        for entity in entities:
            entity_id = entity["id"]
            mention_count = mentions.get(entity_id, 0)
            if mention_count == 0:
                add("missing_source", entity, "当前实体没有关联的来源块")
            elif entity_id not in linked:
                add("isolated", entity, "实体只有来源出现，尚未建立受控语义关系")
            if float(entity["confidence"] or 0) < 0.6:
                add("low_confidence", entity, "实体抽取置信度低于 60%")
            if not str(entity["entity_type"] or "").strip():
                add("uncontrolled_type", entity, "实体缺少受控类型")
            if not str(entity.get("description") or "").strip():
                add("missing_description", entity, "实体缺少说明描述")

            name_key = self._normalized_entity_name(entity["canonical_name"])
            duplicate_ids = [value for value in canonical_groups.get(name_key, []) if value != entity_id]
            duplicate_ids += [value for value in alias_groups.get(name_key, []) if value != entity_id]
            duplicate_ids = sorted(set(duplicate_ids))
            if duplicate_ids:
                add("duplicate_candidate", entity, "规范名称或别名与其他实体重合，需人工确认", duplicate_ids)

        for alias_key, entity_ids in alias_groups.items():
            normalized_ids = sorted(set(entity_ids))
            if len(normalized_ids) > 1:
                for entity_id in normalized_ids:
                    matched_entity = by_id.get(entity_id)
                    if matched_entity:
                        add(
                            "alias_conflict",
                            matched_entity,
                            "同一别名映射到多个规范实体",
                            [value for value in normalized_ids if value != entity_id],
                        )

        for dangling_id in sorted(dangling_relations):
            # Attach an orphaned relation to the first entity only as a visible
            # repair signal; the relation ID itself remains untouched.
            if entities:
                add("dangling_relation", entities[0], f"发现关系端点「{dangling_id}」已不存在")
        return sorted(issues, key=lambda item: (item["status"] != "pending", item["rule"], item["entity_name"]))

    def _quality(self, store: SemanticStore, params: dict):
        query = str(params.get("query", "") or "").strip().casefold()
        status = str(params.get("status", "pending") or "pending")
        if status not in {"pending", "reviewed", "all"}:
            status = "pending"
        issues = self._quality_issues(store)
        counts = dict.fromkeys(
            (
                "missing_source",
                "isolated",
                "low_confidence",
                "uncontrolled_type",
                "missing_description",
                "dangling_relation",
                "alias_conflict",
                "duplicate_candidate",
            ),
            0,
        )
        for issue in issues:
            if issue["status"] == "pending":
                counts[issue["rule"]] += 1
        filtered = [
            issue
            for issue in issues
            if (status == "all" or issue["status"] == status)
            and (
                not query
                or query in f"{issue['entity_name']} {issue['reason']} {' '.join(issue['candidate_names'])}".casefold()
            )
        ]
        limit, offset = self._page(params)
        return {
            "success": True,
            "tab": "quality",
            "items": filtered[offset : offset + limit],
            "total": len(filtered),
            "limit": limit,
            "offset": offset,
            "status": status,
            "counts": counts,
        }

    def _review_entity_quality(self, params):
        issue_id = str(params.get("id", "") or "")
        status = str(params.get("status", "reviewed") or "reviewed")
        if not issue_id or status not in {"pending", "reviewed"}:
            return {"success": False, "message": "参数不完整"}
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        issue = next((item for item in self._quality_issues(store) if item["id"] == issue_id), None)
        if issue is None:
            return {"success": False, "message": "质量问题已失效，请刷新后重试"}
        payload = json.dumps(issue, ensure_ascii=False, sort_keys=True)
        with store.connect() as conn:
            before_row = conn.execute("SELECT * FROM review_queue WHERE id = ?", (issue_id,)).fetchone()
            conn.execute(
                """INSERT INTO review_queue(id, item_kind, payload_json, reason, status, created_at)
                   VALUES(?, 'entity_quality', ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json,
                                                reason = excluded.reason, status = excluded.status""",
                (issue_id, payload, issue["reason"], status, store._now()),
            )
            SemanticStore._audit(
                conn,
                action="review_quality" if status == "reviewed" else "restore_quality",
                object_kind="entity_quality",
                object_id=issue_id,
                before=dict(before_row) if before_row else {},
                after={
                    "status": status,
                    "rule": issue["rule"],
                    "entity_id": issue["entity_id"],
                    "fingerprint": issue["fingerprint"],
                },
            )
        return {"success": True, "id": issue_id, "status": status}

    def _enqueue_entity_quality(self, params):
        issue_id = str(params.get("id", "") or "")
        store = self._store()
        if not issue_id or store is None or not store.path.exists():
            return {"success": False, "message": "参数不完整或语义数据库不存在"}
        issue = next((item for item in self._quality_issues(store) if item["id"] == issue_id), None)
        if issue is None:
            return {"success": False, "message": "质量问题已失效，请刷新后重试"}
        payload = json.dumps(issue, ensure_ascii=False, sort_keys=True)
        with store.connect() as conn:
            existing = conn.execute("SELECT * FROM review_queue WHERE id = ?", (issue_id,)).fetchone()
            conn.execute(
                """INSERT INTO review_queue(id, item_kind, payload_json, reason, status, created_at)
                   VALUES(?, 'entity_quality', ?, ?, 'pending', ?)
                   ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json,
                                                reason = excluded.reason, status = 'pending'""",
                (issue_id, payload, issue["reason"], store._now()),
            )
            SemanticStore._audit(
                conn,
                action="enqueue_quality",
                object_kind="entity_quality",
                object_id=issue_id,
                before=dict(existing) if existing else {},
                after={
                    "status": "pending",
                    "rule": issue["rule"],
                    "entity_id": issue["entity_id"],
                    "fingerprint": issue["fingerprint"],
                },
            )
        return {"success": True, "id": issue_id}

    def _get_entity_merge_preview(self, params):
        source_id = str(params.get("source_id", "") or "")
        target_id = str(params.get("target_id", "") or "")
        store = self._store()
        if not source_id or not target_id or source_id == target_id or store is None or not store.path.exists():
            return {"success": False, "message": "请选择两个不同的实体"}
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT id, canonical_name, entity_type FROM entities WHERE id IN (?, ?)", (source_id, target_id)
            ).fetchall()
            if len(rows) != 2:
                return {"success": False, "message": "实体不存在"}
            entities = {row["id"]: dict(row) for row in rows}
            impact = {}
            for entity_id in (source_id, target_id):
                impact[entity_id] = {
                    "mentions": conn.execute(
                        "SELECT count(*) FROM semantic_mentions WHERE object_kind = 'entity' AND object_id = ?",
                        (entity_id,),
                    ).fetchone()[0],
                    "aliases": [
                        row["alias"]
                        for row in conn.execute(
                            "SELECT alias FROM entity_aliases WHERE entity_id = ? ORDER BY alias", (entity_id,)
                        )
                    ],
                    "relations": conn.execute(
                        "SELECT count(*) FROM relations WHERE source_id = ? OR target_id = ?", (entity_id, entity_id)
                    ).fetchone()[0],
                }
        return {
            "success": True,
            "source": entities[source_id],
            "target": entities[target_id],
            "impact": impact,
            "message": "这是只读影响预览；确认前不会修改任何实体、证据或 Notes。",
        }

    def _merge_entities(self, params):
        source_id = str(params.get("source_id", "") or "")
        target_id = str(params.get("target_id", "") or "")
        if params.get("confirmed") is not True:
            return {"success": False, "message": "需要明确确认后才能合并实体"}
        store = self._store()
        if not source_id or not target_id or source_id == target_id or store is None or not store.path.exists():
            return {"success": False, "message": "请选择两个不同的实体"}
        affected_topics: set[str] = set()
        affected_concept_ids: set[str] = set()
        with store.connect() as conn:
            rows = conn.execute("SELECT * FROM entities WHERE id IN (?, ?)", (source_id, target_id)).fetchall()
            if len(rows) != 2:
                return {"success": False, "message": "实体不存在"}
            entities = {row["id"]: dict(row) for row in rows}
            source, target = entities[source_id], entities[target_id]
            before = {"source": source, "target": target}
            # Preserve every unique mention while avoiding the composite-PK collision.
            conn.execute(
                """DELETE FROM semantic_mentions WHERE object_id = ? AND object_kind = 'entity'
                   AND block_id IN (SELECT block_id FROM semantic_mentions WHERE object_id = ? AND object_kind = 'entity')""",
                (source_id, target_id),
            )
            conn.execute(
                "UPDATE semantic_mentions SET object_id = ? WHERE object_id = ? AND object_kind = 'entity'",
                (target_id, source_id),
            )
            aliases = [
                row["alias"]
                for row in conn.execute("SELECT alias FROM entity_aliases WHERE entity_id = ?", (source_id,))
            ]
            if source["canonical_name"].casefold() != target["canonical_name"].casefold():
                aliases.append(source["canonical_name"])
            for alias in aliases:
                existing = conn.execute(
                    "SELECT entity_id FROM entity_aliases WHERE alias = ? COLLATE NOCASE", (alias,)
                ).fetchone()
                if existing is None:
                    conn.execute(
                        "INSERT INTO entity_aliases(alias, entity_id, created_at) VALUES(?, ?, ?)",
                        (alias, target_id, store._now()),
                    )
                elif existing["entity_id"] == source_id:
                    conn.execute(
                        "UPDATE entity_aliases SET entity_id = ? WHERE alias = ? COLLATE NOCASE", (target_id, alias)
                    )
            conn.execute("UPDATE relations SET source_id = ? WHERE source_id = ?", (target_id, source_id))
            conn.execute("UPDATE relations SET target_id = ? WHERE target_id = ?", (target_id, source_id))
            # Re-key only relations touched by this merge. The former unscoped
            # `source_id = target_id` delete removed every self-loop in the DB,
            # including relations belonging to unrelated entities.
            touched_relations = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM relations WHERE source_id = ? OR target_id = ?",
                    (target_id, target_id),
                )
            ]
            conn.executemany(
                "DELETE FROM relations WHERE id = ?",
                ((row["id"],) for row in touched_relations),
            )
            deduplicated_relations: dict[tuple, dict] = {}
            for relation in touched_relations:
                if relation["source_id"] == relation["target_id"]:
                    continue
                key = (
                    relation["source_id"],
                    relation["relation_type"],
                    relation["target_id"],
                    relation.get("evidence_id"),
                    relation.get("block_id"),
                )
                current = deduplicated_relations.get(key)
                if current is None or float(relation["confidence"]) > float(current["confidence"]):
                    deduplicated_relations[key] = relation
            for relation in deduplicated_relations.values():
                origin_id = relation.get("block_id") or relation.get("evidence_id") or relation["id"]
                relation_id = stable_id(
                    "relation",
                    origin_id,
                    relation["source_id"],
                    relation["relation_type"],
                    relation["target_id"],
                )
                conn.execute(
                    """INSERT INTO relations(
                           id, source_id, relation_type, target_id, confidence, evidence_id, block_id
                       ) VALUES(?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET confidence = MAX(relations.confidence, excluded.confidence),
                                                    evidence_id = excluded.evidence_id,
                                                    block_id = excluded.block_id""",
                    (
                        relation_id,
                        relation["source_id"],
                        relation["relation_type"],
                        relation["target_id"],
                        relation["confidence"],
                        relation.get("evidence_id"),
                        relation.get("block_id"),
                    ),
                )
            conn.execute(
                "UPDATE review_queue SET status = 'reviewed' WHERE item_kind = 'entity_quality' AND payload_json LIKE ?",
                (f'%"entity_id": "{source_id}"%',),
            )
            conn.execute("DELETE FROM entities WHERE id = ?", (source_id,))
            affected_topics = {
                row["topic"]
                for row in conn.execute(
                    """SELECT DISTINCT d.topic FROM semantic_mentions m
                       JOIN blocks b ON b.id = m.block_id JOIN documents d ON d.id = b.document_id
                       WHERE m.object_id = ? AND m.object_kind = 'entity' AND d.topic != ''""",
                    (target_id,),
                )
            }
            related_ids = {
                row["other_id"]
                for row in conn.execute(
                    """SELECT CASE WHEN source_id = ? THEN target_id ELSE source_id END AS other_id
                       FROM relations WHERE source_id = ? OR target_id = ?""",
                    (target_id, target_id, target_id),
                )
            }
            affected_concept_ids = (
                {
                    row["id"]
                    for row in conn.execute(
                        "SELECT id FROM concepts WHERE id IN ({}) AND status = 'active'".format(
                            ",".join("?" for _ in related_ids) or "''"
                        ),
                        tuple(related_ids),
                    )
                }
                if related_ids
                else set()
            )
            after = {"merged_into": target_id, "source_id": source_id, "aliases_added": aliases}
            SemanticStore._audit(
                conn, action="merge_entity", object_kind="entity", object_id=target_id, before=before, after=after
            )
        materialized = []
        try:
            from sidecar.semantic.object_wiki import materialize_object_collection
            from sidecar.semantic.topic_state import materialize_topic_state
            from sidecar.semantic.wiki import materialize_topic_wiki_page

            for topic in sorted(affected_topics):
                materialize_topic_state(store, topic)
                materialize_topic_wiki_page(store, topic)
                materialized.append(topic)
            materialize_object_collection(store, "entity")
            if affected_concept_ids:
                materialize_object_collection(store, "concept")
        except OSError as exc:
            return {"success": False, "message": f"实体已合并，但语义页重建失败：{exc}"}
        return {
            "success": True,
            "target_id": target_id,
            "affected_topics": materialized,
            "message": f"已将「{source['canonical_name']}」合并到「{target['canonical_name']}」",
        }

    def _links(self, params: dict):
        workspace, err = self._require_workspace()
        if err:
            return err
        path = Path(workspace) / ".links.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"links": []}
        except (OSError, json.JSONDecodeError) as exc:
            return {"success": False, "message": f"读取链接索引失败: {exc}"}
        status = str(params.get("status", "all") or "all")
        query = str(params.get("query", "") or "").strip().casefold()
        raw_links = data.get("links", []) or []
        directed_pairs = {(str(item.get("from", "") or ""), str(item.get("to", "") or "")) for item in raw_links}
        links = []
        seen = set()
        for raw in raw_links:
            source = str(raw.get("from", "") or "")
            target = str(raw.get("to", "") or "")
            key = (source, target)
            if not source or not target or source == target or key in seen:
                continue
            seen.add(key)
            item_status = str(raw.get("status", "confirmed") or "confirmed")
            if status != "all" and item_status != status:
                continue
            haystack = f"{source} {target} {raw.get('reason', '')}".casefold()
            if query and query not in haystack:
                continue
            reverse = (target, source) in directed_pairs
            links.append({**raw, "from": source, "to": target, "status": item_status, "has_reverse": reverse})
        limit, offset = self._page(params)
        total = len(links)
        return {
            "success": True,
            "tab": "links",
            "items": links[offset : offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
            "last_scan": data.get("last_scan"),
        }

    def register_routes(self, router):
        router.register("get_semantic_workbench", self._get_workbench)
        router.register("get_semantic_detail", self._get_detail)
        router.register("get_note_semantic_context", self._get_note_semantic_context)
        router.register("get_semantic_compile_status", self._get_compile_status)
        router.register("get_semantic_changes", self._get_changes)
        router.register("get_topic_brief", self._get_topic_brief)
        router.register("start_semantic_full_compile", self._start_full_compile)
        router.register("start_semantic_claims_compile", self._start_claims_compile)
        router.register("review_semantic_conflict", self._review_conflict)
        router.register("scan_semantic_conflicts", self._scan_conflicts)
        router.register("review_semantic_entity_quality", self._review_entity_quality)
        router.register("enqueue_semantic_entity_quality", self._enqueue_entity_quality)
        router.register("get_semantic_entity_merge_preview", self._get_entity_merge_preview)
        router.register("merge_semantic_entities", self._merge_entities)
        router.register("update_semantic_claim", self._update_claim)
        router.register("set_semantic_claim_status", self._set_claim_status)
        router.register("set_semantic_evidence_status", self._set_evidence_status)
        router.register("add_semantic_entity_alias", self._add_entity_alias)
        router.register("verify_semantic_claim", self._verify_claim)
        router.register("get_semantic_topic_wiki_page", self._get_topic_wiki_page)
        router.register("get_semantic_object_wiki_page", self._get_object_wiki_page)
        router.register("publish_semantic_object_wiki_page", self._publish_object_wiki_page)
        router.register("publish_semantic_topic_wiki_page", self._publish_topic_wiki_page)
