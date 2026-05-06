"""Tauri Python sidecar: JSON-RPC over stdin/stdout with workspace file watcher."""

import json
import sys
import threading
from pathlib import Path

from config import config
from modules.file_converter import FileConverterManager
from modules.file_preview import FilePreviewer
from modules.topic_extractor import TopicExtractor
from modules.web_downloader import WebDownloader
from sidecar.mixins.config_mixin import ConfigMixin
from sidecar.mixins.files_mixin import FilesMixin
from sidecar.mixins.intel_mixin import IntelMixin
from sidecar.mixins.links_mixin import LinksMixin
from sidecar.mixins.path_helpers import PathHelpersMixin
from sidecar.mixins.tags_mixin import TagsMixin
from sidecar.mixins.topics_mixin import TopicsMixin
from sidecar.mixins.transfer_mixin import TransferMixin
from sidecar.mixins.workspace_mixin import WorkspaceMixin


class SidecarServer(
    PathHelpersMixin,
    ConfigMixin,
    WorkspaceMixin,
    TransferMixin,
    FilesMixin,
    TagsMixin,
    TopicsMixin,
    LinksMixin,
    IntelMixin,
):
    _watchdog_missing_logged = False

    def __init__(self):
        self.web_downloader = WebDownloader()
        self.file_converter = FileConverterManager()
        self.file_previewer = FilePreviewer()
        self.note_integration = None
        self.topic_extractor = TopicExtractor()
        self._progress_callback = None
        self._running_tasks = set()
        self._running_tasks_lock = threading.Lock()
        self._stdout_lock = threading.Lock()
        self._watcher_observer = None
        self._watcher_debounce_timer = None
        self._watcher_debounce_lock = threading.Lock()
        self._link_discovery_lock = threading.Lock()
        # 查询缓存：工作区路径 → 缓存数据
        self._cache = {}  # key → (workspace_path, data)
        self._cache_lock = threading.Lock()
        self._start_workspace_watcher()

    def _send_response(self, resp):
        with self._stdout_lock:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    def _send_progress(self, element_id, progress, message):
        self._send_response(
            {
                "id": "event",
                "result": {
                    "type": "progress",
                    "element_id": element_id,
                    "progress": progress,
                    "message": message,
                },
            }
        )

    def _start_task(self, task_name, target, args=(), kwargs=None):
        with self._running_tasks_lock:
            if task_name in self._running_tasks:
                return False
            self._running_tasks.add(task_name)

        def _wrapped():
            try:
                target(*args, **(kwargs or {}))
            finally:
                with self._running_tasks_lock:
                    self._running_tasks.discard(task_name)

        threading.Thread(target=_wrapped, daemon=True).start()
        return True

    def _start_workspace_watcher(self):
        workspace = config.workspace_path
        if workspace and Path(workspace).exists():
            self._setup_watcher(workspace)

    def _setup_watcher(self, workspace_path):
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            if not SidecarServer._watchdog_missing_logged:
                SidecarServer._watchdog_missing_logged = True
                sys.stderr.write(
                    "[sidecar] watchdog 未安装，工作区文件变更不会触发 UI 自动刷新。"
                    " 请安装项目依赖（含 watchdog）：uv sync 或 pip install -e .\n"
                )
                sys.stderr.flush()
            return

        self._stop_watcher()

        server = self

        class WorkspaceHandler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    server._on_workspace_file_changed("created", event.src_path)

            def on_deleted(self, event):
                if not event.is_directory:
                    server._on_workspace_file_changed("deleted", event.src_path)

            def on_moved(self, event):
                if not event.is_directory:
                    server._on_workspace_file_changed("moved", event.dest_path, src_path=event.src_path)

            def on_modified(self, event):
                if not event.is_directory:
                    server._on_workspace_file_changed("modified", event.src_path)

        try:
            observer = Observer()
            observer.schedule(WorkspaceHandler(), workspace_path, recursive=True)
            observer.daemon = True
            observer.start()
            self._watcher_observer = observer
        except Exception as e:
            sys.stderr.write(f"[watcher] start failed: {e}\n")
            sys.stderr.flush()

    def _stop_watcher(self):
        if self._watcher_observer:
            try:
                self._watcher_observer.stop()
                self._watcher_observer.join(timeout=2)
            except Exception:
                pass
            self._watcher_observer = None

    def _invalidate_cache(self):
        """文件变更时失效所有缓存"""
        with self._cache_lock:
            self._cache.clear()

    def _cached_or_compute(self, key, compute_fn):
        """通用缓存包装器：按工作区路径失效"""
        workspace = config.workspace_path
        with self._cache_lock:
            if key in self._cache:
                cached_workspace, cached_data = self._cache[key]
                if cached_workspace == workspace:
                    return cached_data
        data = compute_fn()
        with self._cache_lock:
            self._cache[key] = (workspace, data)
        return data

    def _on_workspace_file_changed(self, change_type, file_path, src_path=None):
        path = Path(file_path)
        if path.name.startswith("."):
            return
        suffix = path.suffix.lower()
        if suffix not in (
            ".md",
            ".txt",
            ".pdf",
            ".docx",
            ".pptx",
            ".html",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".svg",
        ):
            return

        with self._watcher_debounce_lock:
            if self._watcher_debounce_timer:
                try:
                    self._watcher_debounce_timer.cancel()
                except RuntimeError:
                    pass
            self._watcher_debounce_timer = threading.Timer(3.0, self._emit_workspace_change)
            self._watcher_debounce_timer.start()

    def _emit_workspace_change(self):
        self._invalidate_cache()
        self._send_response({"id": "event", "result": {"type": "workspace_files_changed"}})

    _ASYNC_METHODS = frozenset(
        {
            "sync_wiki_with_files",
            "batch_auto_assign_topics",
            "start_note_integration",
            "start_file_conversion",
            "extract_topics",
            "llm_rewrite_stream",
            "ai_topic_survey",
        }
    )

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
            "import_files": self._import_files,
            "reveal_in_finder": self._reveal_in_finder,
            "delete_file": self._delete_file,
            "start_file_conversion": self._start_file_conversion,
            "extract_topics": self._extract_topics,
            "start_note_integration": self._start_note_integration,
            "get_file_preview": self._get_file_preview,
            "can_preview_file": self._can_preview_file,
            "save_file_content": self._save_file_content,
            "read_file_raw": self._read_file_raw,
            "get_workspace_tree": self._get_workspace_tree,
            "get_all_tags": self._get_all_tags,
            "get_topic_tree": self._get_topic_tree,
            "auto_tag_files": self._auto_tag_files,
            "save_tags_md": self._save_tags_md,
            "ensure_tags_md": self._ensure_tags_md,
            "create_tag": self._create_tag,
            "rename_tag": self._rename_tag,
            "delete_tag": self._delete_tag,
            "auto_assign_topic": self._auto_assign_topic,
            "batch_auto_assign_topics": self._batch_auto_assign_topics,
            "create_topic": self._create_topic,
            "get_pending_topics": self._get_pending_topics,
            "resolve_topic": self._resolve_topic,
            "rename_topic": self._rename_topic,
            "move_file_to_topic": self._move_file_to_topic,
            "move_file": self._move_file,
            "add_tag_to_file": self._add_tag_to_file,
            "test_api_connection": self._test_api_connection,
            "llm_rewrite": self._llm_rewrite,
            "llm_rewrite_stream": self._llm_rewrite_stream,
            "llm_rewrite_apply": self._llm_rewrite_apply,
            "search_files": self._search_files,
            "on_file_selected": self._on_file_selected,
            "refresh_log": self._refresh_log,
            "discover_links": self._discover_links,
            "get_backlinks": self._get_backlinks,
            "get_relation_graph": self._get_relation_graph,
            "confirm_link": self._confirm_link,
            "reject_link": self._reject_link,
            "confirm_all_links": self._confirm_all_links,
            "sync_wiki_with_files": self._sync_wiki_with_files,
            "delete_topic": self._delete_topic,
            "ai_topic_analyze": self._ai_topic_analyze,
            "ai_topic_survey": self._ai_topic_survey,
            "apply_topic_suggestion": self._apply_topic_suggestion,
        }

        handler = handler_map.get(method)
        if handler:
            if method in self._ASYNC_METHODS:

                def _run_async():
                    try:
                        result = handler(params)
                        self._send_response({"id": req_id, "result": result})
                    except Exception as e:
                        self._send_response({"id": req_id, "error": str(e)})

                threading.Thread(target=_run_async, daemon=True).start()
            else:
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
            self._send_response({"id": req_id, "error": f"Unknown method: {method}"})


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
