"""Scan workspace for ingest work: convert / classify / index pending files."""

from __future__ import annotations

from pathlib import Path

from config import is_ignored_dir
from config.settings import NOTES_FOLDER, RAW_FOLDER
from modules.file_converter import FileConverterManager
from utils.topic.file_ops import check_topic_needs_processing
from utils.wiki_store import topic_from_notes_path


def scan_convert_pending(workspace: str) -> list[str]:
    """Workspace files awaiting conversion (shared by ingest + transfer paths)."""
    supported = set(FileConverterManager.get_supported_formats())
    ws = Path(workspace)
    pending: list[str] = []
    for f in ws.rglob("*"):
        if not f.is_file() or f.name.startswith("."):
            continue
        rel = f.relative_to(ws)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if RAW_FOLDER in rel.parts:
            continue
        if f.suffix.lower() in supported:
            pending.append(str(f))
    return pending


def _scan_index_pending(workspace: str) -> list[Path]:
    """Markdown under Notes/ whose mtime differs from last indexed state."""
    from sidecar.rag.index_state import file_needs_index

    ws = Path(workspace)
    out: list[Path] = []
    for md in ws.rglob("*.md"):
        if (
            md.name.startswith(".")
            or any(part.startswith(".") for part in md.relative_to(ws).parts[:-1])
            or "wiki" in md.parts
        ):
            continue
        if md.name.endswith("_综述.md"):
            continue
        if NOTES_FOLDER not in md.parts:
            continue
        try:
            rel = str(md.relative_to(ws))
            if file_needs_index(rel, md.stat().st_mtime, workspace):
                out.append(md)
        except OSError:
            continue
    return out


def _scan_classify_pending(workspace: str) -> list[Path]:
    ws = Path(workspace)
    out: list[Path] = []
    for md in ws.rglob("*.md"):
        if md.name.startswith(".") or "wiki" in md.parts:
            continue
        if any(is_ignored_dir(p) for p in md.parts):
            continue
        if md.name.endswith("_综述.md") or md.name.endswith("综述.md"):
            continue
        if md.name == "schema.md" or NOTES_FOLDER not in md.parts:
            continue
        from sidecar.workspace_meta import is_inbox_orphan_path, is_workspace_meta_path

        if is_workspace_meta_path(md):
            continue
        if not is_inbox_orphan_path(md, workspace):
            continue
        try:
            from utils.text_utils import parse_frontmatter

            text = md.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(text)
            if topic_from_notes_path(md):
                continue
            if not is_inbox_orphan_path(md, workspace):
                continue
            if fm is None or check_topic_needs_processing(fm):
                out.append(md)
        except OSError:
            continue
    return out
