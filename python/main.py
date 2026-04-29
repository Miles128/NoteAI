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
        self._running_tasks = set()

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

    def _start_task(self, task_name, target, args=(), kwargs=None):
        if task_name in self._running_tasks:
            return False
        self._running_tasks.add(task_name)

        def _wrapped():
            try:
                target(*args, **(kwargs or {}))
            finally:
                self._running_tasks.discard(task_name)

        threading.Thread(target=_wrapped, daemon=True).start()
        return True

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
            "on_file_selected": self._on_file_selected,
            "refresh_log": self._refresh_log,
        }

        handler = handler_map.get(method)
        if handler:
            try:
                result = handler(params)
                self._send_response({"id": req_id, "result": result})
            except Exception as e:
                import traceback
                sys.stderr.write(f"[ERROR] Handler exception: {e}\n")
                sys.stderr.write(traceback.format_exc())
                sys.stderr.flush()
                self._send_response({"id": req_id, "error": str(e)})
        else:
            sys.stderr.write(f"[ERROR] Unknown method: {method}\n")
            sys.stderr.flush()
            self._send_response({"id": req_id, "error": f"Unknown method: {method}"})

    def _get_api_config(self, params):
        api_key = config.api_key or ""
        if len(api_key) > 12:
            masked = api_key[:4] + "■■■■" + api_key[-4:]
        elif api_key:
            masked = "■■■■"
        else:
            masked = ""
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
        api_key = params.get("api_key", "")
        api_base = params.get("api_base", "https://api.openai.com/v1")
        model_name = params.get("model_name", "gpt-4")

        if "■■■■" in api_key:
            api_key = config.api_key

        if not api_key or not api_key.strip():
            return {"success": False, "message": "API Key 不能为空"}

        from utils.helpers import test_api_connection
        connected, conn_msg = test_api_connection(api_key, api_base, model_name)
        if not connected:
            return {"success": False, "message": conn_msg}

        config.api_key = api_key
        config.api_base = api_base
        config.model_name = model_name
        config.temperature = params.get("temperature", 0.7)
        config.max_tokens = params.get("max_tokens", 32000)
        config.max_context_tokens = params.get("max_context_tokens", 128000)

        save_ok, save_msg = config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True, "message": f"配置已保存，{conn_msg}"}

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
        save_ok, save_msg = config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True, "message": "UI 配置已保存"}

    def _get_theme_preference(self, params):
        return config.theme_preference

    def _save_theme_preference(self, params):
        config.theme_preference = params.get("theme", "system")
        save_ok, save_msg = config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
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
        path = params.get("path", config.workspace_path)
        if path and Path(path).exists():
            return {"is_valid": True, "message": "工作区路径有效", "path": path}
        return {"is_valid": False, "message": "工作区路径无效", "path": path}

    def _clear_saved_workspace(self, params):
        from config.settings import WorkspaceStateManager
        WorkspaceStateManager.clear()
        config.workspace_path = ""
        save_ok, save_msg = config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True, "message": "已清除保存的工作区"}

    def _set_workspace_path(self, params):
        path = params.get("path", "")
        if path and Path(path).exists():
            config.workspace_path = path
            save_ok, save_msg = config.save()
            if not save_ok:
                return {"success": False, "message": save_msg}
            self.file_previewer.workspace_path = path
            return {"success": True, "message": "工作区已设置", "workspace_path": path}
        return {"success": False, "message": "路径无效"}

    def _start_web_download(self, params):
        urls = params.get("urls", [])
        ai_assist = params.get("ai_assist", False)
        include_images = params.get("include_images", True)
        save_path = config.workspace_path
        if not save_path:
            return {"success": False, "message": "请先设置工作区"}
        if not urls:
            return {"success": False, "message": "请输入至少一个URL"}

        if not self._start_task("web_download", self._do_web_download, args=(urls, save_path, ai_assist, include_images)):
            return {"success": False, "message": "下载任务正在进行中，请稍后"}

        return {"success": True, "message": "下载已开始"}

    def _do_web_download(self, urls, save_path, ai_assist, include_images):
        try:
            def progress_cb(current, total, message):
                self._send_progress("web-progress", current / total if total > 0 else 0, message)

            self.web_downloader.progress_callback = progress_cb
            self.web_downloader.ai_assist = ai_assist
            self.web_downloader.include_images = include_images
            result = self.web_downloader.download_batch(urls, save_path)
            success_count = sum(1 for r in result if r.get("success"))
            self._send_response({
                "id": "event",
                "result": {"type": "web_download_complete", "success_count": success_count, "total": len(result), "data": result}
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] web_download: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "web_download_error", "error": str(e)}
            })

    def _start_file_conversion(self, params):
        ai_assist = params.get("ai_assist", False)
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        if not self._start_task("file_conversion", self._do_file_conversion, args=(workspace, ai_assist)):
            return {"success": False, "message": "转换任务正在进行中，请稍后"}

        return {"success": True, "message": "转换已开始"}

    def _do_file_conversion(self, workspace, ai_assist):
        try:
            result = self.file_converter.convert_folder(
                workspace, ai_assist=ai_assist
            )
            self._send_response({
                "id": "event",
                "result": {"type": "file_conversion_complete", "data": result}
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] file_conversion: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "file_conversion_error", "error": str(e)}
            })

    def _extract_topics(self, params):
        topic_count = params.get("topic_count", None)
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        result = self.topic_extractor.extract_topics(
            workspace, topic_count=topic_count
        )
        if not result.get("success"):
            return {"success": False, "message": result.get("error", "提取主题失败")}
        return result

    def _start_note_integration(self, params):
        auto_topic = params.get("auto_topic", True)
        topics = params.get("topics", [])
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        self.note_integration = NoteIntegration(workspace)

        if not self._start_task("note_integration", self._do_note_integration, args=(auto_topic, topics)):
            return {"success": False, "message": "整合任务正在进行中，请稍后"}

        return {"success": True, "message": "整合已开始"}

    def _do_note_integration(self, auto_topic, topics):
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
            import traceback
            sys.stderr.write(f"[ERROR] note_integration: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "note_integration_error", "error": str(e)}
            })

    def _get_file_preview(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        result = self.file_previewer.get_preview_data(full_path)
        return result

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
            return {"success": False, "message": str(e)}

    def _on_file_selected(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        return {"success": True, "path": full_path}

    def _refresh_log(self, params):
        return {"success": True, "message": "日志已刷新"}

    def _resolve_path(self, path):
        if not path:
            return path
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
            api_key = params.get("api_key", config.api_key or "")
            api_base = params.get("api_base", config.api_base or "https://api.openai.com/v1")
            model_name = params.get("model_name", config.model_name or "gpt-4")
            if "■■■■" in api_key:
                api_key = config.api_key
            connected, conn_msg = test_api_connection(api_key, api_base, model_name)
            if connected:
                return {"success": True, "message": conn_msg}
            else:
                return {"success": False, "message": conn_msg}
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
