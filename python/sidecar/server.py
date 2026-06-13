"""Tauri Python sidecar: JSON-RPC over stdin/stdout with workspace file watcher."""

import importlib
import json
import sys
import threading
from pathlib import Path

from config import config, is_ignored_dir
from config.settings import NOTES_FOLDER
from modules.file_converter import FileConverterManager
from modules.file_preview import FilePreviewer
from modules.topic_extractor import TopicExtractor
from modules.web_downloader import WebDownloader
from sidecar.handlers import (
    AgentHandler,
    CloudSyncHandler,
    ConfigHandler,
    FilesHandler,
    IngestHandler,
    KbHandler,
    IntelHandler,
    LinksHandler,
    RagHandler,
    TagsHandler,
    TopicsHandler,
    TransferHandler,
    WorkspaceHandler,
)
from sidecar.schema_manager import ensure_schema
from sidecar.mixins.path_helpers import PathHelpersMixin
from sidecar.rag.model_preload import ModelWarmupManager
from sidecar.rpc_router import RpcRouter
from sidecar.service_context import ServiceContext
from utils.fulltext_index import fulltext_index
from utils.logger import logger
from utils.topic_assigner import (
    auto_process_md_file,
)
from sidecar.wiki_utils import (
    sync_wiki_with_files,
)
from utils.ttl_cache import TTLCache

WATCHED_WORKSPACE_SUFFIXES = {".md", ".txt", ".pdf", ".docx", ".pptx", ".html", ".doc", ".ppt"}


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
        self._watcher_needs_wiki_sync = False
        self._watcher_changed_paths: set[str] = set()
        self._watcher_debounce_lock = threading.Lock()
        self._link_discovery_lock = threading.Lock()
        self._cache = TTLCache(ttl=300, max_size=500)
        self._cache_lock = threading.Lock()  # retained for _cached_or_compat compat
        self._router = RpcRouter(send_response=self._send_response)
        self._ctx = ServiceContext(config=config, logger=logger)
        self._config_handler = ConfigHandler(self)
        self._workspace_handler = WorkspaceHandler(self)
        self._transfer_handler = TransferHandler(self)
        self._files_handler = FilesHandler(self)
        self._tags_handler = TagsHandler(self)
        self._topics_handler = TopicsHandler(self)
        self._links_handler = LinksHandler(self)
        self._intel_handler = IntelHandler(self)
        self._rag_handler = RagHandler(self)
        self._cloud_sync_handler = CloudSyncHandler(self)
        self._ingest_handler = IngestHandler(self)
        self._kb_handler = KbHandler(self)
        self._agent_handler = AgentHandler(self)
        self._build_router()
        self._start_workspace_watcher()
        self._startup_sync()

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
        self._rag_handler.register_routes(self._router)
        self._cloud_sync_handler.register_routes(self._router)
        self._ingest_handler.register_routes(self._router)
        self._kb_handler.register_routes(self._router)
        self._agent_handler.register_routes(self._router)

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

    def _startup_sync(self):
        workspace = config.workspace_path
        if not workspace or not Path(workspace).exists():
            return
        try:
            ensure_schema(workspace)
            from sidecar.schema_manager import needs_schema_setup

            if not needs_schema_setup(workspace):
                sync_wiki_with_files()
                logger.info("[startup] WIKI.md synced with workspace")
            else:
                logger.info("[startup] schema setup pending, skip WIKI sync")
        except Exception as e:
            logger.warning(f"[startup] sync failed: {e}")
        self._send_response(
            {
                "id": "event",
                "result": {"type": "workspace_files_changed"},
            }
        )

    def _setup_watcher(self, workspace_path):
        try:
            events_module = importlib.import_module("watchdog.events")
            observers_module = importlib.import_module("watchdog.observers")
            FileSystemEventHandler = events_module.FileSystemEventHandler
            Observer = observers_module.Observer
        except ImportError:
            if not SidecarServer._watchdog_missing_logged:
                SidecarServer._watchdog_missing_logged = True
                logger.warning(
                    "[sidecar] watchdog 未安装，工作区文件变更不会触发 UI 自动刷新。"
                    " 请安装项目依赖（含 watchdog）：uv sync 或 pip install -e ."
                )
            return

        self._stop_watcher()

        server = self

        class WorkspaceHandler(FileSystemEventHandler):
            def on_created(self, event):
                server._on_workspace_file_changed("created", event.src_path, is_directory=event.is_directory)

            def on_deleted(self, event):
                server._on_workspace_file_changed("deleted", event.src_path, is_directory=event.is_directory)

            def on_moved(self, event):
                server._on_workspace_file_changed(
                    "moved",
                    event.dest_path,
                    src_path=event.src_path,
                    is_directory=event.is_directory,
                )

            def on_modified(self, event):
                if not event.is_directory:
                    server._on_workspace_file_changed("modified", event.src_path, is_directory=False)

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

    @staticmethod
    def _rel_parts(file_path: str) -> tuple[str, ...]:
        workspace = config.workspace_path
        path = Path(file_path)
        try:
            return path.relative_to(workspace).parts if workspace else path.parts
        except ValueError:
            return path.parts

    @staticmethod
    def _is_hidden_or_ignored(rel_parts: tuple[str, ...]) -> bool:
        return any(part.startswith(".") for part in rel_parts) or any(is_ignored_dir(part) for part in rel_parts)

    def _is_relevant_workspace_change(self, file_path, is_directory=False):
        path = Path(file_path)
        rel_parts = self._rel_parts(path)
        if self._is_hidden_or_ignored(rel_parts):
            return False
        if "wiki" in rel_parts:
            return False
        if is_directory:
            return True
        return path.suffix.lower() in WATCHED_WORKSPACE_SUFFIXES

    def _workspace_change_affects_wiki(self, change_type, file_path, src_path=None, is_directory=False):
        if change_type not in ("created", "deleted", "moved"):
            return False

        for changed_path in (file_path, src_path):
            if not changed_path:
                continue
            path = Path(changed_path)
            rel_parts = self._rel_parts(path)
            if not rel_parts or rel_parts[0] != NOTES_FOLDER:
                continue
            if self._is_hidden_or_ignored(rel_parts):
                continue
            if is_directory or path.suffix.lower() == ".md":
                return True
        return False

    def _track_watcher_path(self, file_path: str | None) -> None:
        if not file_path:
            return
        path = Path(file_path)
        if not path.is_file() or path.suffix.lower() != ".md":
            return
        rel_parts = self._rel_parts(path)
        if not rel_parts or "wiki" in rel_parts or self._is_hidden_or_ignored(rel_parts):
            return
        with self._watcher_debounce_lock:
            self._watcher_changed_paths.add(str(Path(*rel_parts)))

    def _on_workspace_file_changed(self, change_type, file_path, src_path=None, is_directory=False):
        if not self._is_relevant_workspace_change(file_path, is_directory=is_directory) and (
            not src_path or not self._is_relevant_workspace_change(src_path, is_directory=is_directory)
        ):
            return

        if not is_directory:
            if change_type in ("created", "modified", "moved"):
                self._track_watcher_path(file_path)
            if change_type == "moved" and src_path:
                self._track_watcher_path(src_path)

        path = Path(file_path)
        if not is_directory and change_type in ("created", "moved") and path.suffix.lower() == ".md":
            rel_parts = self._rel_parts(path)
            if not self._is_hidden_or_ignored(rel_parts):
                self._auto_process_md_file(str(path))

        with self._watcher_debounce_lock:
            if self._workspace_change_affects_wiki(change_type, file_path, src_path, is_directory=is_directory):
                self._watcher_needs_wiki_sync = True
            if self._watcher_debounce_timer:
                try:
                    self._watcher_debounce_timer.cancel()
                except RuntimeError:
                    logger.warning("[watcher] debounce timer already cancelled")
            self._watcher_debounce_timer = threading.Timer(5.0, self._emit_workspace_change)
            self._watcher_debounce_timer.start()

    def _auto_process_md_file(self, file_path):
        def _send_event(event_dict):
            self._send_response({"id": "event", "result": event_dict})

        def _mark_wiki_sync():
            with self._watcher_debounce_lock:
                self._watcher_needs_wiki_sync = True

        auto_process_md_file(file_path, send_event=_send_event, mark_wiki_sync=_mark_wiki_sync)

    def _emit_workspace_change(self):
        self._invalidate_cache()
        needs_wiki_sync = False
        changed_paths: list[str] = []
        with self._watcher_debounce_lock:
            needs_wiki_sync = self._watcher_needs_wiki_sync
            self._watcher_needs_wiki_sync = False
            changed_paths = sorted(self._watcher_changed_paths)
            self._watcher_changed_paths.clear()
        if needs_wiki_sync:
            try:
                sync_wiki_with_files()
            except Exception as e:
                logger.warning(f"[watcher] syncing WIKI after workspace change: {e}\n")
        self._send_response(
            {
                "id": "event",
                "result": {
                    "type": "workspace_files_changed",
                    "file_paths": changed_paths,
                },
            }
        )

    def handle_request(self, request):
        self._router.handle(request)


def main():
    server = SidecarServer()
    logger.warning("[Python Sidecar] Ready")

    ModelWarmupManager.start_preload()

    for raw_line in sys.stdin:
        request_line = raw_line.strip()
        if not request_line:
            continue
        try:
            request = json.loads(request_line)
            server.handle_request(request)
        except json.JSONDecodeError as e:
            server._send_response({"id": "", "error": f"Invalid JSON: {e}"})
        except Exception as e:
            server._send_response({"id": "", "error": str(e)})


if __name__ == "__main__":
    main()
