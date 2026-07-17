"""Read-only semantic workbench queries and explicit review actions."""

from __future__ import annotations

import json
from pathlib import Path

from sidecar import job_status
from sidecar.handlers.base import BaseHandler
from sidecar.semantic.store import SemanticStore


class SemanticHandler(BaseHandler):
    _TABS = {"overview", "claims", "concepts", "entities", "conflicts", "links"}
    _COMPILE_JOB_ID = "semantic-full-compile"

    def _store(self) -> SemanticStore | None:
        workspace = self.config.workspace_path
        return SemanticStore(workspace) if workspace else None

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
        return self._semantic_list(store, tab, params)

    @staticmethod
    def _empty_overview() -> dict:
        return {
            "documents": 0,
            "blocks": 0,
            "concepts": 0,
            "entities": 0,
            "claims": 0,
            "evidence": 0,
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
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}
        paths = self._all_note_paths()
        started = self._start_task(
            self._COMPILE_JOB_ID,
            self._run_full_compile,
            args=(workspace, paths),
            kind="semantic_compile",
            label="全库语义编译",
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

    def _run_full_compile(self, workspace: str, paths: list[Path]) -> None:
        from sidecar.semantic.compiler import compile_semantic_batch

        total = max(len(paths), 1)

        def progress(current, _total, message):
            self._send_job_update(
                self._COMPILE_JOB_ID,
                progress=current / total,
                message=message,
                metadata={"processed_documents": current, "total_documents": len(paths)},
            )

        stats = compile_semantic_batch(workspace, paths, progress_cb=progress)
        self._send_job_update(
            self._COMPILE_JOB_ID,
            progress=1,
            status="complete",
            message=f"全库语义编译完成：{stats['documents']} 篇，失败块 {stats['failed_blocks']}",
            metadata={
                "processed_documents": stats["documents"],
                "total_documents": len(paths),
                "blocks": stats["blocks"],
                "claims": stats["claims"],
                "failed_blocks": stats["failed_blocks"],
                "pending_documents": stats["pending_documents"],
                "failure_count": len(stats["failures"]),
            },
        )

    def _get_compile_status(self, _params):
        return {
            "success": True,
            "job": job_status.get_job(self._COMPILE_JOB_ID),
            "total_documents": len(self._all_note_paths()),
        }

    def _semantic_list(self, store: SemanticStore, tab: str, params: dict):
        limit, offset = self._page(params)
        query = str(params.get("query", "") or "").strip()
        like = f"%{query}%"
        with store.connect() as conn:
            if tab == "claims":
                where = "WHERE c.status = 'active' AND (? = '' OR c.statement LIKE ? OR c.scope LIKE ?)"
                args = (query, like, like)
                total = conn.execute(f"SELECT count(*) FROM claims c {where}", args).fetchone()[0]
                rows = conn.execute(
                    f"""SELECT c.id, c.statement, c.scope, c.claim_type, c.confidence,
                               count(e.id) AS evidence_count
                        FROM claims c JOIN evidence e ON e.claim_id = c.id
                        {where} GROUP BY c.id ORDER BY c.confidence DESC, c.statement LIMIT ? OFFSET ?""",
                    (*args, limit, offset),
                ).fetchall()
                items = []
                for row in rows:
                    item = dict(row)
                    evidence = conn.execute(
                        """SELECT e.id, d.path, d.title, d.topic, b.id AS block_id,
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
                    """SELECT e.id, d.path, d.title, d.topic, b.id AS block_id,
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
        item["sources"] = [self._evidence_row(value) for value in rows]
        return {"success": True, "kind": kind, "item": item}

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
        return {"success": True, "tab": "conflicts", "items": items, "total": total, "limit": limit, "offset": offset, "status": status}

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

    def _links(self, params: dict):
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}
        path = Path(workspace) / ".links.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"links": []}
        except (OSError, json.JSONDecodeError) as exc:
            return {"success": False, "message": f"读取链接索引失败: {exc}"}
        status = str(params.get("status", "all") or "all")
        query = str(params.get("query", "") or "").strip().casefold()
        raw_links = data.get("links", []) or []
        directed_pairs = {
            (str(item.get("from", "") or ""), str(item.get("to", "") or ""))
            for item in raw_links
        }
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
        router.register("get_semantic_compile_status", self._get_compile_status)
        router.register("start_semantic_full_compile", self._start_full_compile)
        router.register("review_semantic_conflict", self._review_conflict)
