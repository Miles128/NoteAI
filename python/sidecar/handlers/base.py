
from sidecar.pending_topics import load_pending_topics, save_pending_topics

# 允许代理到 server 的属性白名单
_PROXY_ALLOWED = {
    '_send_response', '_send_progress', '_start_task', '_resolve_path',
    '_start_workspace_watcher', '_stop_watcher', '_invalidate_cache',
    '_cached_or_compute', '_auto_process_md_file',
    '_do_cascade_survey_update', '_batch_auto_assign_topics',
    '_do_file_added_cascade',
    'web_downloader', 'file_converter', 'file_previewer', 'topic_extractor',
    'note_integration',
}


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
    def logger(self):
        return self._ctx.logger

    def __getattr__(self, name):
        if name.startswith('_') and name not in _PROXY_ALLOWED:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        if name in _PROXY_ALLOWED:
            return getattr(self._server, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @staticmethod
    def _parse_frontmatter(md_text: str) -> dict:
        from sidecar.textutils import parse_frontmatter
        return parse_frontmatter(md_text)

    def _load_pending_topics(self):
        if not self.config.workspace_path:
            return []
        return load_pending_topics()

    def _save_pending_topics(self, pending):
        if not self.config.workspace_path:
            return
        save_pending_topics(pending)

    def register_routes(self, router):
        raise NotImplementedError
