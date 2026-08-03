"""RPC: ingest pipeline and legacy schema aliases."""

from __future__ import annotations

import traceback
from typing import Any

from sidecar.handlers.base import BaseHandler
from sidecar.ingest_pipeline import (
    cancel_generation,
    load_ingest_state,
    prepare_auto_ingest,
    request_cancel,
    run_ingest,
)
from sidecar.schema_manager import (
    _load_bundled_schema_template,
    ensure_schema,
    finalize_schema_content,
    load_schema_text,
    save_schema_text,
)
from sidecar.workspace_rules import (
    get_workspace_rules_options,
    load_workspace_rules,
    needs_workspace_rules_setup,
    save_workspace_rules_options,
)
from utils.logger import logger


class IngestHandler(BaseHandler):
    def register_routes(self, router) -> None:
        router.register("ensure_schema", self._ensure_schema)
        router.register("get_schema", self._get_schema)
        router.register("save_schema", self._save_schema)
        router.register("get_schema_rules", self._get_schema_rules)
        router.register("get_schema_options", self._get_schema_options)
        router.register("save_schema_options", self._save_schema_options)
        router.register("needs_schema_setup", self._needs_schema_setup)
        router.register("get_schema_template", self._get_schema_template)
        router.register("start_ingest", self._start_ingest)
        router.register("ensure_ingest", self._ensure_ingest)
        router.register("request_full_ingest", self._request_full_ingest)
        router.register("cancel_ingest", self._cancel_ingest)
        router.register("retry_ingest", self._retry_ingest)
        router.register("get_ingest_status", self._get_ingest_status)
        router.register("check_ingest_updates", self._check_ingest_updates)

    def ensure_running(self, file_paths: list | None = None) -> dict:
        """Start ingest when needed; safe to call on every app/workspace open."""
        workspace, err = self._require_workspace(extra={"started": False}, message="请先设置工作区")
        if err:
            return err

        plan = prepare_auto_ingest(workspace, file_paths=file_paths)
        if plan.get("action") != "start":
            return {"success": True, "started": False, **plan}

        mode = plan.get("mode", "incremental")
        paths = plan.get("file_paths") or []
        resume = bool(plan.get("resume"))
        cancel_token = cancel_generation()
        if self._start_task(
            "ingest_pipeline",
            self._do_ingest,
            args=(mode, paths, resume, cancel_token),
            kind="ingest",
            label="Ingest pipeline",
        ):
            return {
                "success": True,
                "started": True,
                "mode": mode,
                "resume": resume,
                "message": "入库流水线已自动启动",
            }
        return {"success": True, "started": False, "reason": "already_running"}

    def _ensure_ingest(self, params):
        file_paths = params.get("file_paths") or []
        return self.ensure_running(file_paths=file_paths or None)

    def _request_full_ingest(self, _params):
        from sidecar.ingest_pipeline import request_full_ingest

        request_full_ingest()
        return {"success": True, "message": "已标记下次全量入库"}

    def _ensure_schema(self, _params):
        path = ensure_schema()
        if not path:
            return {"success": False, "message": "未设置工作区"}
        return {"success": True, "path": str(path)}

    def _get_schema(self, _params):
        return {"success": True, "content": load_schema_text()}

    def _save_schema(self, params):
        content = params.get("content", "")
        if not content.strip():
            return {"success": False, "message": "内容为空"}
        content = finalize_schema_content(content)
        if not save_schema_text(content):
            return {"success": False, "message": "未设置工作区"}
        return {"success": True, "message": "schema.md 已保存", "needs_setup": False}

    def _needs_schema_setup(self, _params):
        flag = needs_workspace_rules_setup()
        return {"success": True, "needs_setup": flag}

    def _get_schema_template(self, _params):
        return {"success": True, "content": _load_bundled_schema_template()}

    def _get_schema_rules(self, _params):
        return {"success": True, "rules": load_workspace_rules()}

    def _get_schema_options(self, _params):
        opts = get_workspace_rules_options()
        return {"success": True, **opts}

    def _save_schema_options(self, params):
        options = {
            "max_topic_depth": params.get("max_topic_depth", 3),
            "auto_update_survey": params.get("auto_update_survey", True),
            "survey_at_level": params.get("survey_at_level", 2),
        }
        if not save_workspace_rules_options(options):
            return {"success": False, "message": "未设置工作区"}
        return {"success": True, "message": "整理规则已保存", "needs_setup": False}

    def _start_ingest(self, params):
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err

        mode = params.get("mode", "full")
        file_paths = params.get("file_paths") or []
        resume = bool(params.get("resume"))
        cancel_token = cancel_generation()
        if not self._start_task(
            "ingest_pipeline",
            self._do_ingest,
            args=(mode, file_paths, resume, cancel_token),
            kind="ingest",
            label="Ingest pipeline",
        ):
            return {"success": False, "message": "入库流水线正在运行中"}

        return {"success": True, "message": "入库流水线已开始", "mode": mode}

    def _do_ingest(
        self,
        mode: str,
        file_paths: list,
        resume: bool = False,
        cancel_token: int | None = None,
    ) -> None:
        def send_progress(stage: str, progress: float, message: str, extra: dict | None = None) -> None:
            self._send_job_update(
                "ingest_pipeline",
                progress=progress,
                message=message,
                metadata={"stage": stage, **(extra or {})},
            )
            payload = {
                "type": "ingest_progress",
                "stage": stage,
                "progress": progress,
                "message": message,
            }
            if extra:
                payload.update(extra)
            self._send_response({"id": "event", "result": payload})

        def send_event(resp: dict) -> None:
            self._send_response(resp)

        try:
            result = run_ingest(
                mode=mode,
                file_paths=file_paths or None,
                send_progress=send_progress,
                send_event=send_event,
                resume=resume,
                cancel_after_generation=cancel_token,
            )
            if result.get("success"):
                cascade_topics = result.get("stats", {}).get("cascade_topics") or []
                self._send_job_update(
                    "ingest_pipeline",
                    progress=1.0,
                    message="入库流水线完成",
                    status="complete",
                    metadata={"stats": result.get("stats", {})},
                )
                self._start_background_surveys(cascade_topics)
            elif result.get("cancelled"):
                self._send_job_update("ingest_pipeline", status="cancelled", message="入库已取消")
            else:
                self._send_job_update(
                    "ingest_pipeline",
                    status="failed",
                    message=result.get("message", "入库失败"),
                    metadata={"stats": result.get("stats", {})},
                )
        except Exception as e:
            logger.warning(f"[ingest] pipeline error: {e}\n{traceback.format_exc()}")
            self._send_response(
                {
                    "id": "event",
                    "result": {"type": "ingest_complete", "success": False, "error": str(e)},
                }
            )

    def _start_background_surveys(self, topics: list[str]) -> None:
        unique_topics = []
        seen: set[str] = set()
        for topic in topics or []:
            topic = str(topic or "").strip()
            if topic and topic not in seen:
                seen.add(topic)
                unique_topics.append(topic)
        if not unique_topics:
            return
        self._start_task(
            "ingest_cascade_surveys",
            self._do_background_surveys,
            args=(unique_topics,),
            kind="survey",
            label="Background surveys",
        )

    def _do_background_surveys(self, topics: list[str]) -> None:
        from sidecar.cascade_runner import retry_failed_cascades, run_cascade_for_topics
        from sidecar.ingest_pipeline import load_ingest_state, save_ingest_state

        def progress_cb(cur: int, total: int, message: str) -> None:
            progress = cur / total if total else 1
            self._send_job_update(
                "ingest_cascade_surveys",
                progress=progress,
                message=message,
                metadata={"topics": topics},
            )
            self._send_response(
                {
                    "id": "event",
                    "result": {
                        "type": "ingest_progress",
                        "stage": "cascade",
                        "progress": progress,
                        "message": message,
                        "background": True,
                    },
                }
            )

        def send_event(resp: dict) -> None:
            self._send_response(resp)

        self._send_response(
            {
                "id": "event",
                "result": {
                    "type": "ingest_cascade_started",
                    "topics": topics,
                },
            }
        )
        result = run_cascade_for_topics(topics, send_response=send_event, progress_cb=progress_cb)
        retry_result = retry_failed_cascades(send_response=send_event)
        updated = result.get("updated", 0) + retry_result.get("updated", 0)
        failed = list(result.get("failed") or []) + list(retry_result.get("failed") or [])
        state: dict[str, Any] = load_ingest_state()
        raw_stats = state.get("stats")
        stats: dict[str, Any] = raw_stats if isinstance(raw_stats, dict) else {}
        stats["cascade_updated"] = updated
        stats["cascade_failed"] = failed
        state["stats"] = stats
        save_ingest_state(state)
        self._send_job_update(
            "ingest_cascade_surveys",
            progress=1.0,
            status="failed" if failed else "complete",
            message="后台综述完成" if not failed else "后台综述部分失败",
            metadata={"updated": updated, "failed": failed},
        )
        self._send_response(
            {
                "id": "event",
                "result": {
                    "type": "ingest_cascade_complete",
                    "success": not failed,
                    "updated": updated,
                    "failed": failed,
                },
            }
        )

    def _cancel_ingest(self, _params):
        request_cancel()
        self._send_job_update("ingest_pipeline", status="cancelled", message="已请求取消")
        return {"success": True, "message": "已请求取消"}

    def _retry_ingest(self, params):
        state = load_ingest_state()
        file_paths = params.get("file_paths") or state.get("file_paths") or []
        if state.get("status") == "cancelled":
            mode = params.get("mode") or state.get("mode") or "full"
            cancel_token = cancel_generation()
            if self._start_task(
                "ingest_pipeline",
                self._do_ingest,
                args=(mode, file_paths, True, cancel_token),
                kind="ingest",
                label="Ingest pipeline",
            ):
                return {"success": True, "started": True, "mode": mode, "resume": True}
            return {"success": False, "started": False, "reason": "already_running"}
        return self.ensure_running(file_paths=file_paths or None)

    def _check_ingest_updates(self, params):
        workspace, err = self._require_workspace(extra={"has_updates": False}, message="请先设置工作区")
        if err:
            return err

        plan = prepare_auto_ingest(workspace, file_paths=params.get("file_paths") or None)
        has_updates = plan.get("action") == "start"
        return {
            "success": True,
            "has_updates": has_updates,
            "message": "发现可整理更新" if has_updates else "已是最新",
            **plan,
        }

    def _get_ingest_status(self, _params):
        state = load_ingest_state()
        status = state.get("status", "idle")
        return {
            "success": True,
            "status": status,
            "stage": state.get("stage", ""),
            "progress": state.get("progress", 0),
            "message": state.get("message", ""),
            "stats": state.get("stats", {}),
            "running": status == "running",
            "needs_resume": status in ("interrupted", "failed"),
            "can_retry": status in ("failed", "cancelled", "interrupted", "complete"),
        }
