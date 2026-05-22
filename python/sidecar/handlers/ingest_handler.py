"""RPC: schema.md and unified ingest pipeline."""

from __future__ import annotations

import traceback

from sidecar.handlers.base import BaseHandler
from sidecar.ingest_pipeline import (
    clear_cancel,
    load_ingest_state,
    request_cancel,
    run_ingest,
)
from sidecar.schema_manager import (
    _load_bundled_schema_template,
    ensure_schema,
    finalize_schema_content,
    load_schema_text,
    needs_schema_setup,
    parse_schema_rules,
    save_schema_text,
)
from utils.logger import logger


class IngestHandler(BaseHandler):
    def register_routes(self, router) -> None:
        router.register("ensure_schema", self._ensure_schema)
        router.register("get_schema", self._get_schema)
        router.register("save_schema", self._save_schema)
        router.register("get_schema_rules", self._get_schema_rules)
        router.register("needs_schema_setup", self._needs_schema_setup)
        router.register("get_schema_template", self._get_schema_template)
        router.register("start_ingest", self._start_ingest)
        router.register("cancel_ingest", self._cancel_ingest)
        router.register("retry_ingest", self._retry_ingest)
        router.register("get_ingest_status", self._get_ingest_status)

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
        return {"success": True, "needs_setup": needs_schema_setup()}

    def _get_schema_template(self, _params):
        return {"success": True, "content": _load_bundled_schema_template()}

    def _get_schema_rules(self, _params):
        return {"success": True, "rules": parse_schema_rules()}

    def _start_ingest(self, params):
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        mode = params.get("mode", "full")
        file_paths = params.get("file_paths") or []
        if not self._start_task("ingest_pipeline", self._do_ingest, args=(mode, file_paths)):
            return {"success": False, "message": "入库流水线正在运行中"}

        return {"success": True, "message": "入库流水线已开始", "mode": mode}

    def _do_ingest(self, mode: str, file_paths: list) -> None:
        def send_progress(stage: str, progress: float, message: str, extra: dict | None = None) -> None:
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
            run_ingest(
                mode=mode,
                file_paths=file_paths or None,
                send_progress=send_progress,
                send_event=send_event,
            )
        except Exception as e:
            logger.warning(f"[ingest] pipeline error: {e}\n{traceback.format_exc()}")
            self._send_response({
                "id": "event",
                "result": {"type": "ingest_complete", "success": False, "error": str(e)},
            })

    def _cancel_ingest(self, _params):
        request_cancel()
        return {"success": True, "message": "已请求取消"}

    def _retry_ingest(self, params):
        state = load_ingest_state()
        if state.get("status") == "running":
            return {"success": False, "message": "流水线正在运行"}
        clear_cancel()
        mode = params.get("mode", state.get("mode", "full"))
        file_paths = params.get("file_paths") or []
        if not self._start_task("ingest_pipeline", self._do_ingest, args=(mode, file_paths)):
            return {"success": False, "message": "无法启动重试"}
        return {"success": True, "message": "已重新开始入库"}

    def _get_ingest_status(self, _params):
        state = load_ingest_state()
        return {
            "success": True,
            "status": state.get("status", "idle"),
            "stage": state.get("stage", ""),
            "message": state.get("message", ""),
            "stats": state.get("stats", {}),
            "running": state.get("status") == "running",
            "can_retry": state.get("status") in ("failed", "cancelled", "complete"),
        }
