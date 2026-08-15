"""Semantic workbench queries, explicit review actions and claim verification."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sidecar import job_status
from sidecar.handlers.base import BaseHandler
from sidecar.handlers.cli_agent_handler import CliAgentHandler
from sidecar.semantic.detail import list_semantic_objects
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

    def _manifest_prompt_version(self, store: SemanticStore):
        """读取 manifest 中记录的抽取提示词版本（库实际使用的 PROMPT_VERSION）。"""
        manifest_path = store.root / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            import json

            return json.loads(manifest_path.read_text(encoding="utf-8")).get("prompt_version")
        except Exception:
            return None

    def _prompt_version_status(self, store: SemanticStore):
        from sidecar.semantic.extractor import PROMPT_VERSION

        manifest_version = self._manifest_prompt_version(store)
        return {
            "prompt_version": manifest_version,
            "prompt_version_latest": PROMPT_VERSION,
            "prompt_version_stale": (manifest_version is not None and manifest_version != PROMPT_VERSION),
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
                "prompt_version_status": self._prompt_version_status(store),
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
            "prompt_version_status": self._prompt_version_status(store),
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

    def _generate_weekly_brief(self, params):
        """One-click weekly brief for the whole knowledge base.

        LLM-generated when configured; otherwise falls back to a structured
        Markdown digest. Read-only — never writes to the store or Notes.
        """
        from prompts import WEEKLY_BRIEF_PROMPT

        store = self._store()
        if store is None:
            return {"success": False, "message": "未设置工作区"}
        try:
            days = max(1, min(int(params.get("days", 7) or 7), 90))
        except (TypeError, ValueError):
            days = 7
        if not store.path.exists():
            return {
                "success": True,
                "days": days,
                "brief": f"## 知识库周报\n\n过去 {days} 天没有语义变化。",
                "fallback": False,
            }
        try:
            counts = store.change_counts(days=days)
            items, total = store.recent_changes(days=days, limit=60)
        except sqlite3.OperationalError:
            return {
                "success": True,
                "days": days,
                "brief": f"## 知识库周报\n\n过去 {days} 天没有语义变化。",
                "fallback": False,
            }

        if total < 1:
            return {
                "success": True,
                "days": days,
                "brief": f"## 知识库周报\n\n过去 {days} 天没有语义变化。",
                "fallback": False,
            }

        by_kind: dict[str, int] = {}
        by_object: dict[str, int] = {}
        for c in counts:
            by_kind[c["change_kind"]] = by_kind.get(c["change_kind"], 0) + c["count"]
            by_object[c["object_kind"]] = by_object.get(c["object_kind"], 0) + c["count"]
        # 面向普通用户的口语化表述：不暴露内部英文键名。
        kind_label = {
            "added": "新增了知识",
            "updated": "补充/修正了旧内容",
            "invalidated": "存疑或暂时无法确认",
            "removed": "不再收录",
        }
        object_label = {
            "claim": "知识点",
            "entity": "笔记中提到的人/事物",
            "concept": "概念",
            "document": "笔记",
        }
        counts_summary = (
            "\n".join(
                f"- {kind_label.get(kind, kind)}：{n} 条" for kind, n in sorted(by_kind.items(), key=lambda kv: -kv[1])
            )
            + "\n"
            + "\n".join(
                f"- {object_label.get(kind, kind)}：{n} 条"
                for kind, n in sorted(by_object.items(), key=lambda kv: -kv[1])
            )
        )

        records = "\n".join(
            f"- [{c['created_at'][:10]}] {kind_label.get(c['change_kind'], c['change_kind'])}"
            f"（{object_label.get(c['object_kind'], c['object_kind'])}）: {c['label'] or c['object_id']}"
            + (f"（来源：{Path(c['source_path']).name}）" if c.get("source_path") else "")
            for c in items
        )
        brief, fallback = self._compose_weekly_brief(days, counts_summary, records, WEEKLY_BRIEF_PROMPT)
        return {"success": True, "days": days, "brief": brief, "fallback": fallback}

    @staticmethod
    def _compose_weekly_brief(days: int, counts_summary: str, records: str, prompt_template: str) -> tuple[str, bool]:
        """LLM-generated weekly brief when available; structured fallback otherwise."""
        from utils.llm_utils import call_llm_raw

        try:
            prompt = prompt_template.format(days=days, counts_summary=counts_summary, change_records=records)
            text = call_llm_raw(prompt, temperature=0.3)
        except Exception:
            text = ""
        if not text or not text.strip():
            fallback = (
                f"## 知识库周报\n\n"
                f"（未配置 LLM 或生成失败，以下为结构化变化记录）\n\n"
                f"## 统计概览\n\n{counts_summary}\n\n"
                f"## 变化记录\n\n{records}\n"
            )
            return fallback, True
        return text.strip(), False

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
        from utils.note_scanner import iter_note_files

        # 统一走 note_scanner 扫描入口（排除点文件、点目录与 *_综述.md），
        # 与 ingest 语义编译、增量扫描的过滤规则保持一致。
        return sorted(iter_note_files(workspace), key=lambda p: str(p.relative_to(workspace)))

    def _start_full_compile(self, _params):
        return self._start_semantic_compile(_params, claims_only=False)

    def _retry_failed_blocks(self, params):
        claims_only = bool(params.get("claims_only", True))
        try:
            limit = max(1, min(int(params.get("limit", 100)), 500))
        except (TypeError, ValueError):
            limit = 100
        workspace, err = self._require_workspace()
        if err:
            return err
        store = SemanticStore(workspace)
        if not store.path.exists():
            return {"success": False, "message": "语义库不存在"}
        from sidecar.semantic.compiler import retry_failed_blocks

        return retry_failed_blocks(store, claims_only=claims_only, limit=limit)

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
        from sidecar.semantic.compiler import run_full_compile

        def progress(progress_value: float, message: str, metadata: dict) -> None:
            self._send_job_update(self._COMPILE_JOB_ID, progress=progress_value, message=message, metadata=metadata)

        def done(message: str, metadata: dict) -> None:
            self._send_job_update(
                self._COMPILE_JOB_ID, progress=1, status="complete", message=message, metadata=metadata
            )

        run_full_compile(workspace, paths, claims_only=claims_only, progress_cb=progress, done_cb=done)

    def _get_compile_status(self, _params):
        return {
            "success": True,
            "job": job_status.get_job(self._COMPILE_JOB_ID),
            "total_documents": len(self._all_note_paths()),
        }

    def _semantic_list(self, store: SemanticStore, tab: str, params: dict, min_confidence: float | None = None):
        limit, offset = self._page(params)
        query = str(params.get("query", "") or "").strip()
        status = str(params.get("status", "active") or "active")
        return list_semantic_objects(
            store,
            tab,
            query=query,
            status=status,
            limit=limit,
            offset=offset,
            min_confidence=min_confidence,
        )

    def _get_detail(self, params):
        kind = str(params.get("kind", "") or "")
        object_id = str(params.get("id", "") or "")
        if kind not in {"concept", "entity", "claim"} or not object_id:
            return {"success": False, "message": "参数不完整"}
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        from sidecar.semantic.detail import build_object_detail

        return build_object_detail(store, kind, object_id)

    def _verify_claim(self, params):
        """研究核查单个命题（CLI agent 深度研究 / 内置 API LLM reasoning），结果落库。

        method='cli'（默认）：CLI 深度研究，可能耗时数分钟；与 CLI Agent 对话
        共用同一执行通道，复用 CliAgentHandler 的全局锁避免并发执行。
        method='llm'：内置 LLM（DeepSeek reasoning）流式核查，不占用 CLI 通道。
        两种方式都经 send_event 推送研究过程事件（cli_agent_output /
        verify_llm_output），供前端实时展示。
        """
        claim_id = str(params.get("id", "") or "")
        agent_id = str(params.get("agent", "") or "")
        method = str(params.get("method", "") or "").strip().lower()
        if method not in ("cli", "llm"):
            method = "cli"
        if not claim_id or not agent_id:
            return {"success": False, "message": "参数不完整"}
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        claim = store.claims.get_verifiable_claim(claim_id)
        if claim is None:
            return {"success": False, "message": "命题不存在或不可核查（仅支持 active 且有证据的命题）"}
        if method == "llm":
            from sidecar.semantic.claim_verifier import verify_claim_via_llm

            result = verify_claim_via_llm(store, claim, send_event=self._send_response)
            result["output"] = (result.get("output") or "")[-2000:]
            return result
        if not CliAgentHandler._cli_agent_lock.acquire(blocking=False):
            return {"success": False, "message": "CLI agent 正在运行其他任务，请稍后再试"}
        try:
            from sidecar.semantic.claim_verifier import verify_claim_via_cli

            result = verify_claim_via_cli(store, claim, agent_id=agent_id, send_event=self._send_response)
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

    def _quality(self, store: SemanticStore, params: dict):
        from sidecar.semantic.quality import collect_quality_issues

        query = str(params.get("query", "") or "").strip().casefold()
        status = str(params.get("status", "pending") or "pending")
        if status not in {"pending", "reviewed", "all"}:
            status = "pending"
        issues = collect_quality_issues(store)
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
                "cross_kind_duplicate",
                "unlikely_entity_name",
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
        from sidecar.semantic.quality import collect_quality_issues

        issue = next((item for item in collect_quality_issues(store) if item["id"] == issue_id), None)
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
        from sidecar.semantic.quality import collect_quality_issues

        issue = next((item for item in collect_quality_issues(store) if item["id"] == issue_id), None)
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

    def _enqueue_cross_kind_merges(self, params):
        """一次性把全部同名双表（实体↔概念）候选取样入队 Inbox，供人工合并。"""
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        from sidecar.semantic.quality import collect_quality_issues

        count = 0
        for issue in collect_quality_issues(store):
            if issue["rule"] != "cross_kind_duplicate" or issue["status"] != "pending":
                continue
            payload = json.dumps(issue, ensure_ascii=False, sort_keys=True)
            with store.connect() as conn:
                conn.execute(
                    """INSERT INTO review_queue(id, item_kind, payload_json, reason, status, created_at)
                       VALUES(?, 'entity_quality', ?, ?, 'pending', ?)
                       ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json,
                                                     reason = excluded.reason, status = 'pending'""",
                    (issue["id"], payload, issue["reason"], store._now()),
                )
            count += 1
        return {"success": True, "count": count, "message": f"已将 {count} 组同名双表候选加入 Inbox"}

    def _resolve_cross_kind_merges(self, params):
        """用 LLM 批处理裁决 Inbox 中的同名双表候选并自动执行。"""
        store = self._store()
        if store is None or not store.path.exists():
            return {"success": False, "message": "语义数据库不存在"}
        from sidecar.semantic.cross_kind_resolver import resolve_cross_kind_merges

        dry_run = params.get("dry_run") is True
        return resolve_cross_kind_merges(store, dry_run=dry_run)

    def _get_entity_merge_preview(self, params):
        source_id = str(params.get("source_id", "") or "")
        target_id = str(params.get("target_id", "") or "")
        store = self._store()
        if not source_id or not target_id or source_id == target_id or store is None or not store.path.exists():
            return {"success": False, "message": "请选择两个不同的对象"}
        with store.connect() as conn:
            from sidecar.semantic.entity_merge import _KIND_ALIAS_COLUMN, _KIND_ALIASES, _locate

            source = _locate(conn, source_id)
            target = _locate(conn, target_id)
            if source is None or target is None:
                return {"success": False, "message": "对象不存在"}
            objects = {source["id"]: source, target["id"]: target}
            impact = {}
            for obj_id in (source_id, target_id):
                kind = objects[obj_id]["kind"]
                impact[obj_id] = {
                    "mentions": conn.execute(
                        "SELECT count(*) FROM semantic_mentions WHERE object_kind = ? AND object_id = ?",
                        (kind, obj_id),
                    ).fetchone()[0],
                    "aliases": [
                        row["alias"]
                        for row in conn.execute(
                            f"SELECT alias FROM {_KIND_ALIASES[kind]} WHERE {_KIND_ALIAS_COLUMN[kind]} = ? ORDER BY alias",
                            (obj_id,),
                        )
                    ],
                    "relations": conn.execute(
                        "SELECT count(*) FROM relations WHERE source_id = ? OR target_id = ?", (obj_id, obj_id)
                    ).fetchone()[0],
                }
        return {
            "success": True,
            "source": source,
            "target": target,
            "impact": impact,
            "message": "这是只读影响预览；确认前不会修改任何对象、证据或 Notes。",
        }

    def _merge_entities(self, params):
        source_id = str(params.get("source_id", "") or "")
        target_id = str(params.get("target_id", "") or "")
        if params.get("confirmed") is not True:
            return {"success": False, "message": "需要明确确认后才能合并实体"}
        store = self._store()
        if not source_id or not target_id or source_id == target_id or store is None or not store.path.exists():
            return {"success": False, "message": "请选择两个不同的实体"}
        from sidecar.semantic.entity_merge import merge_entities

        return merge_entities(store, source_id, target_id)

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
        router.register("generate_weekly_brief", self._generate_weekly_brief)
        router.register("start_semantic_full_compile", self._start_full_compile)
        router.register("review_semantic_conflict", self._review_conflict)
        router.register("scan_semantic_conflicts", self._scan_conflicts)
        router.register("review_semantic_entity_quality", self._review_entity_quality)
        router.register("enqueue_semantic_entity_quality", self._enqueue_entity_quality)
        router.register("enqueue_cross_kind_semantic_merges", self._enqueue_cross_kind_merges)
        router.register("resolve_cross_kind_merges", self._resolve_cross_kind_merges)
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
        router.register("get_semantic_graph_data", self._get_semantic_graph_data)

    def _get_semantic_graph_data(self, params):
        """语义关系星云图数据（只读）。"""
        from sidecar.semantic.graph_data import get_semantic_graph_data

        workspace = self.config.workspace_path
        try:
            return get_semantic_graph_data(
                workspace,
                scope=str(params.get("scope", "all") or "all"),
                filter_path=str(params.get("filter", "") or ""),
                limit=params.get("limit", 80),
                min_share=params.get("min_share", 2),
                include_docs=bool(params.get("include_docs", False)),
                max_docs=params.get("max_docs", 60),
            )
        except Exception as e:
            return {"success": False, "message": f"语义图谱查询失败: {e}"}
