"""Backup / export / restore / index-health RPCs (local reliability, PRD P1)."""

from __future__ import annotations

from sidecar.handlers.base import BaseHandler


class ReliabilityHandler(BaseHandler):
    def register_routes(self, router):
        router.register("backup_workspace", self._backup_workspace)
        router.register("export_notes", self._export_notes)
        router.register("restore_workspace_backup", self._restore_workspace_backup)
        router.register("get_index_health", self._get_index_health)

    def _workspace(self) -> str | None:
        return self.config.workspace_path

    def _backup_workspace(self, params):
        from sidecar.workspace_backup import backup_workspace

        target_dir = str(params.get("target_dir") or "").strip() or None
        include_derived = bool(params.get("include_derived"))
        return backup_workspace(self._workspace() or "", target_dir=target_dir, include_derived=include_derived)

    def _export_notes(self, params):
        from sidecar.workspace_backup import export_notes

        target_dir = str(params.get("target_dir") or "").strip() or None
        return export_notes(self._workspace() or "", target_dir=target_dir)

    def _restore_workspace_backup(self, params):
        from sidecar.workspace_backup import restore_workspace_backup

        backup_path = str(params.get("backup_path") or "").strip()
        if not backup_path:
            return {"success": False, "message": "未提供备份文件路径"}
        return restore_workspace_backup(self._workspace() or "", backup_path)

    def _get_index_health(self, _params):
        from sidecar.workspace_backup import check_index_health

        return check_index_health(self._workspace() or "")
