"""Path / frontmatter helpers for sidecar (delegates to shared utils).

Handler-facing helpers that mirror these (``_parse_frontmatter``,
``_load_pending_topics``, ``_save_pending_topics``) live on
``sidecar.handlers.base.BaseHandler``; this mixin only hosts the server-level
helpers handlers forward to via ``BaseHandler`` properties.
"""

from sidecar.paths import find_file_by_name_in_workspace, resolve_workspace_path
from sidecar.wiki_utils import parse_wiki_headings as _parse_wiki_headings_impl


class PathHelpersMixin:
    def _resolve_path(self, path):
        return resolve_workspace_path(path)

    def _find_file_by_name(self, path):
        return find_file_by_name_in_workspace(path)

    def _parse_wiki_headings(self):
        return _parse_wiki_headings_impl()
