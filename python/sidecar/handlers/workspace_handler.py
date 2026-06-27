from pathlib import Path

from config import is_ignored_dir
from config.constants import ABSTRACT_FOLDER, NOTES_FOLDER, RAW_FOLDER
from config.settings import workspace_manager
from sidecar.handlers.base import BaseHandler
from utils.logger import logger

FILE_TREE_SUFFIXES = {".md", ".txt", ".pdf", ".docx", ".pptx", ".html", ".doc", ".ppt"}
FILE_TREE_IGNORED_DIRS = {
    "__pycache__",
    "node_modules",
    "target",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tauri",
    ".noteai",
    ".NoteAI",
    "Clippings",
    "rag_index",
    ".rag_index",
    ".ai_memory",
    ".obsidian",
}
ALLOWED_ROOT_DIRS = {NOTES_FOLDER, RAW_FOLDER, ABSTRACT_FOLDER}


class WorkspaceHandler(BaseHandler):
    def register_routes(self, router):
        router.register("get_workspace_status", self._get_workspace_status)
        router.register("check_workspace_path_valid", self._check_workspace_path_valid)
        router.register("clear_saved_workspace", self._clear_saved_workspace)
        router.register("set_workspace_path", self._set_workspace_path)
        router.register("get_workspace_tree", self._get_workspace_tree)
        router.register("on_file_selected", self._on_file_selected)
        router.register("refresh_log", self._refresh_log)
        router.register("get_kb_health", self._get_kb_health)

    def _get_kb_health(self, _params):
        from sidecar.kb_health import compute_kb_health

        return compute_kb_health(self.config.workspace_path)

    def _get_workspace_status(self, _params):
        saved_path, _ = workspace_manager.load_workspace()
        path = saved_path if saved_path and Path(saved_path).exists() else ""
        if path and path != self.config.workspace_path:
            self.config._set_attr("workspace_path", path)
            self._setup_workspace()
            self._setup_watcher(path)
        if path and Path(path).exists():
            from sidecar.workspace_rules import needs_workspace_rules_setup

            self.file_previewer.workspace_path = path
            return {
                "is_set": True,
                "workspace_path": path,
                "notes_folder": str(Path(path) / NOTES_FOLDER),
                "organized_folder": str(Path(path) / ABSTRACT_FOLDER),
                "saved_workspace": True,
                "needs_workspace_rules_setup": needs_workspace_rules_setup(path),
                "needs_schema_setup": needs_workspace_rules_setup(path),
            }
        return {"is_set": False, "saved_workspace": False}

    def _check_workspace_path_valid(self, params):
        path = params.get("path", self.config.workspace_path)
        if path and Path(path).exists():
            return {"is_valid": True, "message": "工作区路径有效", "path": path}
        return {"is_valid": False, "message": "工作区路径无效", "path": path}

    def _clear_saved_workspace(self, _params):
        success, message = workspace_manager.clear_workspace_state()
        if not success:
            return {"success": False, "message": message}
        self.config._set_attr("workspace_path", "")
        return {"success": True, "message": "已清除保存的工作区"}

    def _set_workspace_path(self, params):
        path = params.get("path", "")
        if path and Path(path).exists():
            self.config._set_attr("workspace_path", path)
            self.file_previewer.workspace_path = path
            self._setup_watcher(path)
            self._invalidate_cache()
            save_ok, save_msg = workspace_manager.save_workspace(path)
            if not save_ok:
                return {"success": False, "message": save_msg}
            from sidecar.workspace_rules import needs_workspace_rules_setup

            flag = needs_workspace_rules_setup(path)
            return {
                "success": True,
                "message": "工作区已设置",
                "workspace_path": path,
                "needs_workspace_rules_setup": flag,
                "needs_schema_setup": flag,
            }
        return {"success": False, "message": "路径无效"}

    def _get_workspace_tree(self, _params):
        return self._compute_workspace_tree()

    def _compute_workspace_tree(self):
        workspace = self.config.workspace_path
        if not workspace:
            return []

        ws = Path(workspace)
        items = []
        root_files: list[dict] = []

        try:
            for entry in sorted(ws.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    if entry.name not in ALLOWED_ROOT_DIRS:
                        continue
                    if entry.name == ABSTRACT_FOLDER:
                        children = self._build_flat_tree(entry, ws)
                    else:
                        children = self._build_recursive_tree(entry, ws)
                    items.append(
                        {
                            "name": entry.name,
                            "path": str(entry.relative_to(ws)),
                            "type": "folder",
                            "children": children,
                        }
                    )
                else:
                    if entry.suffix.lower() not in FILE_TREE_SUFFIXES:
                        continue
                    if entry.suffix.lower() == ".md":
                        continue
                    stat = entry.stat()
                    root_files.append(
                        {
                            "name": entry.name,
                            "path": str(entry.relative_to(ws)),
                            "type": "file",
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                        }
                    )
        except PermissionError as e:
            logger.warning(f"[workspace_handler] building workspace tree: {e}")

        return items + root_files

    def _build_flat_tree(self, dir_path: Path, workspace: Path):
        items = []
        try:
            for entry in sorted(dir_path.rglob("*"), key=lambda p: p.name.lower()):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    continue
                if entry.suffix.lower() not in FILE_TREE_SUFFIXES:
                    continue
                if not entry.exists():
                    continue
                rel = str(entry.relative_to(workspace))
                stat = entry.stat()
                items.append(
                    {
                        "name": entry.name,
                        "path": rel,
                        "type": "file",
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )
        except PermissionError as e:
            logger.warning(f"[workspace_handler] building flat tree: {e}")
        return items

    def _build_recursive_tree(self, dir_path: Path, workspace: Path, depth: int = 0):
        # Cap recursion depth to avoid blocking the RPC thread on huge/deep workspaces.
        MAX_TREE_DEPTH = 6
        items = []
        try:
            for entry in sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if entry.name.startswith("."):
                    continue
                rel = str(entry.relative_to(workspace))
                if entry.is_dir():
                    if entry.name in FILE_TREE_IGNORED_DIRS or is_ignored_dir(entry.name):
                        continue
                    children = (
                        self._build_recursive_tree(entry, workspace, depth + 1)
                        if depth < MAX_TREE_DEPTH
                        else []
                    )
                    items.append(
                        {
                            "name": entry.name,
                            "path": rel,
                            "type": "folder",
                            "children": children,
                        }
                    )
                else:
                    if entry.suffix.lower() not in FILE_TREE_SUFFIXES:
                        continue
                    if dir_path.name == NOTES_FOLDER and entry.suffix.lower() == ".md":
                        continue
                    if not entry.exists():
                        continue
                    stat = entry.stat()
                    items.append(
                        {
                            "name": entry.name,
                            "path": rel,
                            "type": "file",
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                        }
                    )
        except PermissionError as e:
            logger.warning(f"[workspace_handler] building recursive tree: {e}")
        return items

    def _on_file_selected(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            full_path = self._find_file_by_name(path)
        if full_path:
            return {"success": True, "path": full_path}
        return {"success": False, "message": "路径无效或不在工作区内"}

    def _refresh_log(self, _params):
        return {"success": True, "message": "日志已刷新"}
