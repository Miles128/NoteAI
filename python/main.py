import sys
import json
import asyncio
import threading
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config import config
from modules.web_downloader import WebDownloader
from modules.file_converter import FileConverterManager
from modules.file_preview import FilePreviewer
from modules.note_integration import NoteIntegration
from modules.topic_extractor import TopicExtractor
from utils.helpers import call_llm, check_api_config, test_api_connection
from utils.tag_extractor import extract_tags_from_filename, add_yaml_frontmatter_to_file


class SidecarServer:
    def __init__(self):
        self.web_downloader = WebDownloader()
        self.file_converter = FileConverterManager()
        self.file_previewer = FilePreviewer()
        self.note_integration = None
        self.topic_extractor = TopicExtractor()
        self._progress_callback = None

    def _send_response(self, resp):
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + '\n')
        sys.stdout.flush()

    def _send_progress(self, element_id, progress, message):
        self._send_response({
            "id": "event",
            "result": {
                "type": "progress",
                "element_id": element_id,
                "progress": progress,
                "message": message
            }
        })

    def handle_request(self, request):
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id", "")

        handler_map = {
            "get_api_config": self._get_api_config,
            "save_api_config": self._save_api_config,
            "get_ui_config": self._get_ui_config,
            "save_ui_config": self._save_ui_config,
            "get_theme_preference": self._get_theme_preference,
            "save_theme_preference": self._save_theme_preference,
            "get_workspace_status": self._get_workspace_status,
            "check_workspace_path_valid": self._check_workspace_path_valid,
            "clear_saved_workspace": self._clear_saved_workspace,
            "set_workspace_path": self._set_workspace_path,
            "start_web_download": self._start_web_download,
            "start_file_conversion": self._start_file_conversion,
            "extract_topics": self._extract_topics,
            "start_note_integration": self._start_note_integration,
            "get_file_preview": self._get_file_preview,
            "can_preview_file": self._can_preview_file,
            "save_file_content": self._save_file_content,
            "get_workspace_tree": self._get_workspace_tree,
            "test_api_connection": self._test_api_connection,
        }

        handler = handler_map.get(method)
        if handler:
            try:
                result = handler(params)
                self._send_response({"id": req_id, "result": result})
            except Exception as e:
                self._send_response({"id": req_id, "error": str(e)})
        else:
            self._send_response({"id": req_id, "error": f"Unknown method: {method}"})

    def _get_api_config(self, params):
        api_key = config.api_key or ""
        masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        return {
            "api_key": masked,
            "api_key_configured": bool(config.api_key),
            "api_base": config.api_base,
            "model_name": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "max_context_tokens": config.max_context_tokens,
        }

    def _save_api_config(self, params):
        if params.get("api_key"):
            config.api_key = params["api_key"]
        if params.get("api_base"):
            config.api_base = params["api_base"]
        if params.get("model_name"):
            config.model_name = params["model_name"]
        if "temperature" in params:
            config.temperature = float(params["temperature"])
        if "max_tokens" in params:
            config.max_tokens = int(params["max_tokens"])
        if "max_context_tokens" in params:
            config.max_context_tokens = int(params["max_context_tokens"])
        config.save()
        return {"success": True, "message": "配置已保存"}

    def _get_ui_config(self, params):
        return {
            "web_ai_assist": config.web_ai_assist,
            "web_include_images": config.web_include_images,
            "conv_ai_assist": config.conv_ai_assist,
            "integration_strategy": config.integration_strategy,
            "auto_topic": config.auto_topic,
            "topic_list": config.topic_list,
        }

    def _save_ui_config(self, params):
        if "web_ai_assist" in params:
            config.web_ai_assist = params["web_ai_assist"]
        if "web_include_images" in params:
            config.web_include_images = params["web_include_images"]
        if "conv_ai_assist" in params:
            config.conv_ai_assist = params["conv_ai_assist"]
        if "integration_strategy" in params:
            config.integration_strategy = params["integration_strategy"]
        if "auto_topic" in params:
            config.auto_topic = params["auto_topic"]
        if "topic_list" in params:
            config.topic_list = params["topic_list"]
        config.save()
        return {"success": True, "message": "UI 配置已保存"}

    def _get_theme_preference(self, params):
        return config.theme_preference

    def _save_theme_preference(self, params):
        config.theme_preference = params.get("theme", "system")
        config.save()
        return {"success": True}

    def _get_workspace_status(self, params):
        path = config.workspace_path
        if path and Path(path).exists():
            self.file_previewer.workspace_path = path
            return {
                "is_set": True,
                "workspace_path": path,
                "notes_folder": str(Path(path) / "Notes"),
                "organized_folder": str(Path(path) / "Organized"),
                "saved_workspace": True,
            }
        return {"is_set": False, "saved_workspace": False}

    def _check_workspace_path_valid(self, params):
        path = config.workspace_path
        if path and Path(path).exists():
            return {"is_valid": True, "message": "工作区路径有效", "path": path}
        return {"is_valid": False, "message": "工作区路径无效", "path": path}

    def _clear_saved_workspace(self, params):
        from config.settings import WorkspaceStateManager
        WorkspaceStateManager.clear()
        config.workspace_path = ""
        config.save()
        return {"success": True, "message": "已清除保存的工作区"}

    def _set_workspace_path(self, params):
        path = params.get("path", "")
        if path and Path(path).exists():
            config.workspace_path = path
            config.save()
            self.file_previewer.workspace_path = path
            return {"success": True, "message": "工作区已设置", "workspace_path": path}
        return {"success": False, "message": "路径无效"}

    def _start_web_download(self, params):
        urls = params.get("urls", [])
        ai_assist = params.get("ai_assist", False)
        include_images = params.get("include_images", True)
        save_path = config.workspace_path
        if not save_path:
            return {"error": "请先设置工作区"}

        def _run():
            try:
                result = self.web_downloader.download_batch(
                    urls, save_path,
                    ai_assist=ai_assist,
                    include_images=include_images
                )
                self._send_response({
                    "id": "event",
                    "result": {"type": "web_download_complete", "data": result}
                })
            except Exception as e:
                self._send_response({
                    "id": "event",
                    "result": {"type": "web_download_error", "error": str(e)}
                })

        threading.Thread(target=_run, daemon=True).start()
        return {"status": "started"}

    def _start_file_conversion(self, params):
        ai_assist = params.get("ai_assist", False)
        workspace = config.workspace_path
        if not workspace:
            return {"error": "请先设置工作区"}

        def _run():
            try:
                result = self.file_converter.convert_folder(
                    workspace, ai_assist=ai_assist
                )
                self._send_response({
                    "id": "event",
                    "result": {"type": "file_conversion_complete", "data": result}
                })
            except Exception as e:
                self._send_response({
                    "id": "event",
                    "result": {"type": "file_conversion_error", "error": str(e)}
                })

        threading.Thread(target=_run, daemon=True).start()
        return {"status": "started"}

    def _extract_topics(self, params):
        topic_count = params.get("topic_count", None)
        workspace = config.workspace_path
        if not workspace:
            return {"error": "请先设置工作区"}

        result = self.topic_extractor.extract_topics(
            workspace, topic_count=topic_count
        )
        return result

    def _start_note_integration(self, params):
        auto_topic = params.get("auto_topic", True)
        topics = params.get("topics", [])
        workspace = config.workspace_path
        if not workspace:
            return {"error": "请先设置工作区"}

        self.note_integration = NoteIntegration(workspace)

        def _run():
            try:
                result = self.note_integration.integrate(
                    auto_topic=auto_topic,
                    topics=topics
                )
                self._send_response({
                    "id": "event",
                    "result": {"type": "note_integration_complete", "data": result}
                })
            except Exception as e:
                self._send_response({
                    "id": "event",
                    "result": {"type": "note_integration_error", "error": str(e)}
                })

        threading.Thread(target=_run, daemon=True).start()
        return {"status": "started"}

    def _get_file_preview(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        return self.file_previewer.get_preview_data(full_path)

    def _can_preview_file(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        return self.file_previewer.can_preview(full_path)

    def _save_file_content(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        try:
            Path(full_path).write_text(params.get("content", ""), encoding="utf-8")
            return {"success": True, "message": "文件已保存"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _resolve_path(self, path):
        if Path(path).is_absolute():
            return path
        workspace = config.workspace_path
        if workspace:
            return str(Path(workspace) / path)
        return path

    def _get_workspace_tree(self, params):
        workspace = config.workspace_path
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
            except PermissionError:
                pass
            return items

        return _build_tree(workspace)

    def _test_api_connection(self, params):
        try:
            result = test_api_connection()
            return {"success": True, "message": "连接成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}


def main():
    server = SidecarServer()
    sys.stderr.write("[Python Sidecar] Ready\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            server.handle_request(request)
        except json.JSONDecodeError as e:
            server._send_response({"id": "", "error": f"Invalid JSON: {e}"})
        except Exception as e:
            server._send_response({"id": "", "error": str(e)})


if __name__ == "__main__":
    main()
