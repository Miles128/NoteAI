"""Path / frontmatter helpers for sidecar (delegates to shared utils)."""

from sidecar.paths import find_file_by_name_in_workspace, resolve_workspace_path
from sidecar.pending_topics import (
    get_pending_topics_path,
    load_pending_topics,
    save_pending_topics,
)
from sidecar.textutils import parse_frontmatter as _parse_frontmatter_impl
from sidecar.wiki_utils import parse_wiki_headings as _parse_wiki_headings_impl


class PathHelpersMixin:
    def _parse_frontmatter(self, text):
        return _parse_frontmatter_impl(text)

    def _resolve_path(self, path):
        return resolve_workspace_path(path)

    def _find_file_by_name(self, path):
        return find_file_by_name_in_workspace(path)

    def _get_pending_topics_path(self):
        return get_pending_topics_path()

    def _load_pending_topics(self):
        return load_pending_topics()

    def _save_pending_topics(self, pending):
        return save_pending_topics(pending)

    def _parse_wiki_headings(self):
        return _parse_wiki_headings_impl()
