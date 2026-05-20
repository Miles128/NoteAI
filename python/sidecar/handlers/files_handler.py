import base64
import importlib
import platform
import subprocess
from pathlib import Path

from sidecar.handlers.base import BaseHandler
from utils.logger import logger
from utils.topic_assigner import sync_wiki_with_files


class FilesHandler(BaseHandler):
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
        return self.file_previewer.get_preview_data(full_path)

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
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        try:
            raw_bytes = Path(full_path).read_bytes()
            return {
                "success": True,
                "content": base64.b64encode(raw_bytes).decode("utf-8"),
                "size": len(raw_bytes),
                "file_name": Path(full_path).name
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _reveal_in_finder(self, params):
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

        file_topic = None
        if full_path.suffix.lower() == '.md':
            try:
                text = full_path.read_text(encoding='utf-8')
                meta, _ = self._parse_frontmatter(text)
                if meta and isinstance(meta.get('topic'), str):
                    file_topic = meta['topic'].strip().strip("'\"")
            except Exception as e:
                logger.warning(f"[files_handler] reading file topic for deletion: {e}\n")

        try:
            send2trash = importlib.import_module("send2trash")
            send2trash.send2trash(str(full_path))

            if full_path.suffix.lower() == '.md':
                try:
                    sync_wiki_with_files()
                except Exception as e:
                    logger.warning(f"[files_handler] syncing WIKI after file deletion: {e}\n")

            if file_topic:
                self._start_task(f"cascade_update_{file_topic}", self._do_cascade_survey_update, args=(file_topic,))

            return {"success": True}
        except ImportError:
            return {"success": False, "message": "未安装 send2trash，无法安全删除文件。请运行: uv pip install send2trash"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def register_routes(self, router):
        router.register("get_file_preview", self._get_file_preview)
        router.register("can_preview_file", self._can_preview_file)
        router.register("save_file_content", self._save_file_content)
        router.register("read_file_raw", self._read_file_raw)
        router.register("reveal_in_finder", self._reveal_in_finder)
        router.register("delete_file", self._delete_file)
