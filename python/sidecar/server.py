"""Tauri Python sidecar: JSON-RPC over stdin/stdout with workspace file watcher."""

import json
import sys
import threading
from pathlib import Path

from config import config
from modules.file_converter import FileConverterManager
from modules.file_preview import FilePreviewer
from sidecar.mixins.path_helpers import PathHelpersMixin
from modules.topic_extractor import TopicExtractor
from modules.web_downloader import WebDownloader
from sidecar.handlers import (
    ConfigHandler,
    FilesHandler,
    IntelHandler,
    IntelTopicHandler,
    LinksHandler,
    RagHandler,
    TagsHandler,
    TopicsHandler,
    TransferHandler,
    WorkspaceHandler,
    BaseHandler,
)
from sidecar.rpc_router import RpcRouter
from sidecar.service_context import ServiceContext
from utils.ttl_cache import TTLCache
from utils.fulltext_index import fulltext_index
from utils.logger import logger as app_logger


class SidecarServer(PathHelpersMixin):
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
        self._cache = TTLCache(ttl=300, max_size=500)
        self._cache_lock = threading.Lock()  # retained for _cached_or_compat compat
        self._router = RpcRouter(send_response=self._send_response)
        self._ctx = ServiceContext(config=config, logger=app_logger)
        self._config_handler = ConfigHandler(self)
        self._workspace_handler = WorkspaceHandler(self)
        self._transfer_handler = TransferHandler(self)
        self._files_handler = FilesHandler(self)
        self._tags_handler = TagsHandler(self)
        self._topics_handler = TopicsHandler(self)
        self._links_handler = LinksHandler(self)
        self._intel_handler = IntelHandler(self)
        self._intel_topic_handler = IntelTopicHandler(self)
        self._rag_handler = RagHandler(self)
        self._build_router()
        self._start_workspace_watcher()

    def _build_router(self):
        self._config_handler.register_routes(self._router)
        self._workspace_handler.register_routes(self._router)
        self._transfer_handler.register_routes(self._router)
        self._files_handler.register_routes(self._router)
        self._tags_handler.register_routes(self._router)
        self._topics_handler.register_routes(self._router)
        self._topics_handler.register_routes_3tier(self._router)
        self._links_handler.register_routes(self._router)
        self._intel_handler.register_routes(self._router)
        self._intel_topic_handler.register_routes(self._router)
        self._rag_handler.register_routes(self._router)

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
            logger.warning(f"[watcher] start failed: {e}\n")

    def _stop_watcher(self):
        if self._watcher_observer:
            try:
                self._watcher_observer.stop()
                self._watcher_observer.join(timeout=2)
            except Exception as e:
                logger.warning(f"[watcher] stop failed: {e}\n")
            self._watcher_observer = None

    def _invalidate_cache(self):
        """文件变更时失效所有缓存"""
        self._cache.clear()
        fulltext_index.mark_dirty()

    def _cached_or_compute(self, key, compute_fn):
        """通用缓存包装器：按工作区路径失效，带 TTL"""
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        data = compute_fn()
        self._cache.set(key, data)
        return data

    def _do_cascade_survey_update(self, topic):
        return self._topics_handler._do_cascade_survey_update(topic)

    def _batch_auto_assign_topics(self, params):
        return self._topics_handler._batch_auto_assign_topics(params)

    def _on_workspace_file_changed(self, change_type, file_path, src_path=None):
        path = Path(file_path)
        if path.name.startswith("."):
            return
        if 'wiki' in path.parts:
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

        if change_type in ("created", "moved") and suffix == ".md":
            workspace = config.workspace_path
            if workspace:
                try:
                    rel = path.relative_to(workspace)
                    from config import is_ignored_dir
                    if not any(is_ignored_dir(p) for p in rel.parts):
                        self._auto_process_md_file(str(path))
                except ValueError:
                    logger.warning(f"[watcher] path outside workspace: {file_path}\n")

        with self._watcher_debounce_lock:
            if self._watcher_debounce_timer:
                try:
                    self._watcher_debounce_timer.cancel()
                except RuntimeError:
                    logger.warning("[watcher] debounce timer already cancelled")
            self._watcher_debounce_timer = threading.Timer(3.0, self._emit_workspace_change)
            self._watcher_debounce_timer.start()

    def _auto_process_md_file(self, file_path):
        import re
        from config.settings import NOTES_FOLDER, ABSTRACT_FOLDER
        from utils.topic_assigner import (
            move_file_to_notes_topic_folder,
            add_file_to_wiki_topic,
            auto_assign_topic_for_file,
            _check_topic_needs_processing,
        )

        try:
            text = Path(file_path).read_text(encoding='utf-8')
        except Exception as e:
            logger.warning(f"[watcher] failed to read {file_path}: {e}\n")
            return

        m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
        yaml_text = m.group(1) if m else ""

        if not m or _check_topic_needs_processing(yaml_text):
            try:
                result = auto_assign_topic_for_file(file_path)
                if result and result.get("status") == "auto_assigned" and result.get("topic"):
                    self._send_response({
                        "id": "event",
                        "result": {
                            "type": "auto_topic_assigned",
                            "file": file_path,
                            "topic": result["topic"],
                        },
                    })
            except Exception as e:
                logger.warning(f"[watcher] auto_assign_topic_for_file failed for {file_path}: {e}\n")
            return

        file_topic = None
        for line in yaml_text.split('\n'):
            idx = line.find(':')
            if idx < 0:
                continue
            key = line[:idx].strip()
            val = line[idx + 1:].strip()
            if key == 'topic' and val:
                file_topic = val.strip().strip("'\"")
                break

        if not file_topic:
            return

        workspace = config.workspace_path
        filename = Path(file_path).stem

        is_survey = filename.endswith('综述') or filename.endswith('_综述')
        if is_survey:
            expected_dir = Path(workspace) / ABSTRACT_FOLDER / file_topic
        else:
            expected_dir = Path(workspace) / NOTES_FOLDER / file_topic

        try:
            in_correct_folder = Path(file_path).is_relative_to(expected_dir)
        except AttributeError:
            in_correct_folder = str(Path(file_path)).startswith(str(expected_dir))

        if not in_correct_folder and not is_survey:
            move_result = move_file_to_notes_topic_folder(file_path, file_topic)
            if move_result.get("success"):
                new_path = move_result.get("new_path", "")
                if new_path:
                    add_file_to_wiki_topic(new_path, file_topic)
                self._send_response({
                    "id": "event",
                    "result": {
                        "type": "auto_file_moved",
                        "file": file_path,
                        "topic": file_topic,
                        "new_path": new_path,
                    },
                })

    def _emit_workspace_change(self):
        self._invalidate_cache()
        self._send_response({"id": "event", "result": {"type": "workspace_files_changed"}})

    def handle_request(self, request):
        self._router.handle(request)


def main():
    from sidecar.rag.model_preload import ModelWarmupManager

    server = SidecarServer()
    logger.warning("[Python Sidecar] Ready")

    ModelWarmupManager.start_preload()

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
