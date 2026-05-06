"""Preview, save, read, reveal, delete (from python/main.py)."""

import json
import re
import sys
import shutil
import threading
from pathlib import Path

import yaml
from config import config, is_ignored_dir

class FilesMixin:
    def _get_file_preview(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            full_path = self._find_file_by_name(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        if not Path(full_path).exists():
            alt = self._find_file_by_name(path)
            if alt:
                full_path = alt
        result = self.file_previewer.get_preview_data(full_path)
        return result

    def _can_preview_file(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            full_path = self._find_file_by_name(path)
        if not full_path:
            return False
        return self.file_previewer.can_preview(full_path)

    def _save_file_content(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        try:
            Path(full_path).write_text(params.get("content", ""), encoding="utf-8")
            return {"success": True, "message": "文件已保存"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _read_file_raw(self, params):
        import base64 as b64
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        try:
            raw_bytes = Path(full_path).read_bytes()
            return {
                "success": True,
                "content": b64.b64encode(raw_bytes).decode("utf-8"),
                "size": len(raw_bytes),
                "file_name": Path(full_path).name
            }
        except Exception as e:
            return {"success": False, "message": str(e)}
    def _reveal_in_finder(self, params):
        import subprocess
        import platform
        path = params.get("path", "")
        if not path or not Path(path).exists():
            return {"success": False, "message": "路径不存在"}
        resolved = self._resolve_path(path)
        if resolved is None:
            return {"success": False, "message": "路径不允许在工作区外"}
        if not Path(resolved).exists():
            return {"success": False, "message": "解析后的路径不存在"}
        path = resolved
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", "-R", path])
            elif platform.system() == "Windows":
                subprocess.Popen(["explorer", "/select,", path])
            else:
                subprocess.Popen(["xdg-open", str(Path(path).parent)])
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _delete_file(self, params):
        path = params.get("path", "")
        if not path:
            return {"success": False, "message": "路径不能为空"}

        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)

        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}

        try:
            import send2trash
            send2trash.send2trash(str(full_path))
            return {"success": True}
        except ImportError:
            return {"success": False, "message": "未安装 send2trash，无法安全删除文件。请运行: uv pip install send2trash"}
        except Exception as e:
            return {"success": False, "message": str(e)}
