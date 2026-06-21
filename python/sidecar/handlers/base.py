from sidecar.pending_topics import load_pending_topics, save_pending_topics


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
    def _start_task(self):
        return self._server._start_task

    @property
    def _resolve_path(self):
        return self._server._resolve_path

    @property
    def _cached_or_compute(self):
        return self._server._cached_or_compute

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
