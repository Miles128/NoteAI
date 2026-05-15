import sys
from pathlib import Path

from config.settings import workspace_manager
from sidecar.handlers.base import BaseHandler


class WorkspaceHandler(BaseHandler):
    def register_routes(self, router):
        router.register("get_workspace_status", self._get_workspace_status)
        router.register("check_workspace_path_valid", self._check_workspace_path_valid)
        router.register("clear_saved_workspace", self._clear_saved_workspace)
        router.register("set_workspace_path", self._set_workspace_path)
        router.register("get_workspace_tree", self._get_workspace_tree)
        router.register("on_file_selected", self._on_file_selected)
        router.register("refresh_log", self._refresh_log)

    def _get_workspace_status(self, params):
        path = self.config.workspace_path
        if not path or not Path(path).exists():
            saved_path, _ = workspace_manager.load_workspace()
            if saved_path and Path(saved_path).exists():
                self.config.workspace_path = saved_path
                self.config.save()
                path = saved_path
                self.config.setup_workspace_folders()
                self._server._setup_watcher(path)
        if path and Path(path).exists():
            self.file_previewer.workspace_path = path
            return {
                "is_set": True,
                "workspace_path": path,
                "notes_folder": str(Path(path) / "Notes"),
                "organized_folder": str(Path(path) / config.ABSTRACT_FOLDER),
                "saved_workspace": True,
            }
        return {"is_set": False, "saved_workspace": False}

    def _check_workspace_path_valid(self, params):
        path = params.get("path", self.config.workspace_path)
        if path and Path(path).exists():
            return {"is_valid": True, "message": "工作区路径有效", "path": path}
        return {"is_valid": False, "message": "工作区路径无效", "path": path}

    def _clear_saved_workspace(self, params):
        success, message = workspace_manager.clear_workspace_state()
        if not success:
            return {"success": False, "message": message}
        self.config.workspace_path = ""
        save_ok, save_msg = self.config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True, "message": "已清除保存的工作区"}

    def _set_workspace_path(self, params):
        path = params.get("path", "")
        if path and Path(path).exists():
            self.config.workspace_path = path
            save_ok, save_msg = self.config.save()
            if not save_ok:
                return {"success": False, "message": save_msg}
            self.file_previewer.workspace_path = path
            self._server._setup_watcher(path)
            self._server._invalidate_cache()
            workspace_manager.save_workspace(path)
            return {"success": True, "message": "工作区已设置", "workspace_path": path}
        return {"success": False, "message": "路径无效"}

    def _get_workspace_tree(self, params):
        return self._cached_or_compute("workspace_tree", self._compute_workspace_tree)

    def _compute_workspace_tree(self):
        workspace = self.config.workspace_path
        if not workspace:
            return []

        def _build_tree(path, prefix=""):
            items = []
            try:
                entries = sorted(Path(path).iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                for entry in entries:
                    if entry.name.startswith('.'):
                        continue
                    rel = str(entry.relative_to(workspace))
                    if entry.is_dir():
                        children = _build_tree(str(entry), rel)
                        items.append({
                            "name": entry.name,
                            "path": rel,
                            "type": "folder",
                            "children": children,
                        })
                    else:
                        stat = entry.stat()
                        items.append({
                            "name": entry.name,
                            "path": rel,
                            "type": "file",
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                        })
            except PermissionError as e:
                sys.stderr.write(f"[workspace_handler] building workspace tree: {e}\n")
                sys.stderr.flush()
            return items

        return _build_tree(workspace)

    def _on_file_selected(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            full_path = self._find_file_by_name(path)
        if full_path:
            return {"success": True, "path": full_path}
        return {"success": False, "message": "路径无效或不在工作区内"}

    def _refresh_log(self, params):
        return {"success": True, "message": "日志已刷新"}