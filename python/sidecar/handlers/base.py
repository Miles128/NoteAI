from utils.topic_pending import load_pending, save_pending

NO_WORKSPACE_MESSAGE = "未设置工作区"


class BaseHandler:
    def __init__(self, server):
        self._server = server

    @property
    def _ctx(self):
        return self._server._ctx

    @property
    def config(self):
        return self._ctx.config

    @property
    def _send_response(self):
        return self._server._send_response

    @property
    def _send_progress(self):
        return self._server._send_progress

    @property
    def _send_job_update(self):
        return self._server._send_job_update

    @property
    def _start_task(self):
        return self._server._start_task

    @property
    def _resolve_path(self):
        return self._server._resolve_path

    @property
    def _find_file_by_name(self):
        return self._server._find_file_by_name

    @property
    def _parse_wiki_headings(self):
        return self._server._parse_wiki_headings

    @property
    def _cached_or_compute(self):
        return self._server._cached_or_compute

    @property
    def _invalidate_cache(self):
        return self._server._invalidate_cache

    @property
    def _setup_watcher(self):
        return self._server._setup_watcher

    @property
    def _setup_workspace(self):
        return self._server.setup_workspace_folders

    @property
    def _do_cascade_survey_update(self):
        return self._server._do_cascade_survey_update

    @property
    def _batch_auto_assign_topics(self):
        return self._server._batch_auto_assign_topics

    @property
    def web_downloader(self):
        return self._server.web_downloader

    @property
    def file_converter(self):
        return self._server.file_converter

    @property
    def file_previewer(self):
        return self._server.file_previewer

    @property
    def topic_extractor(self):
        return self._server.topic_extractor

    @property
    def _link_discovery_lock(self):
        return self._server._link_discovery_lock

    @staticmethod
    def _parse_frontmatter(md_text: str) -> tuple[dict | None, str]:
        """解析 frontmatter，返回 (meta_dict|None, body_str)，与 utils.text_utils.parse_frontmatter 一致。"""
        from utils.text_utils import parse_frontmatter

        return parse_frontmatter(md_text)

    def _require_workspace(self, extra: dict | None = None, message: str = NO_WORKSPACE_MESSAGE):
        """工作区统一守卫。

        Returns:
            (workspace, None) —— 工作区已设置；
            (None, error_dict) —— 未设置，error_dict 可直接作为 RPC 响应返回。
            extra 用于附加字段（如 {"started": False}）。
        """
        workspace = self.config.workspace_path
        if workspace:
            return workspace, None
        err = {"success": False, "message": message}
        if extra:
            err.update(extra)
        return None, err

    def _load_pending_topics(self):
        if not self.config.workspace_path:
            return []
        return load_pending()

    def _save_pending_topics(self, pending):
        if not self.config.workspace_path:
            return
        save_pending(pending)

    def register_routes(self, router):
        raise NotImplementedError
