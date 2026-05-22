"""WIKI.md heading helpers — delegates to utils.wiki_manager for consistency."""

from pathlib import Path

from config import config

from utils.wiki_manager import parse_wiki_headings as _parse_wiki_headings_full


def resolve_wiki_path(workspace_str: str | Path | None = None) -> Path:
    if workspace_str is None:
        workspace_str = config.workspace_path or ""
    ws = Path(workspace_str)
    new_path = ws / "wiki" / "WIKI.md"
    if new_path.exists():
        return new_path
    old_path = ws / "WIKI.md"
    if old_path.exists():
        return old_path
    return new_path


def parse_wiki_headings() -> list:
    return _parse_wiki_headings_full()
