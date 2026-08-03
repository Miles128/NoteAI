"""Idempotency state for source-file to Markdown conversion."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from config import config
from config.settings import NOTES_FOLDER, WORKSPACE_APP_FOLDER
from utils.text_utils import parse_frontmatter

_STATE_LOCK = threading.Lock()
_STATE_FILE = "conversion_state.json"


def source_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state_path(workspace: str | Path) -> Path:
    path = Path(workspace) / WORKSPACE_APP_FOLDER / _STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_unlocked(workspace: str | Path) -> dict:
    path = _state_path(workspace)
    if not path.exists():
        return {"sources": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sources": {}}
    sources = data.get("sources") if isinstance(data, dict) else None
    return {"sources": sources if isinstance(sources, dict) else {}}


def _workspace_rel(path: Path, workspace: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path.resolve())


def _find_note_by_hash(workspace: Path, digest: str) -> Path | None:
    notes = workspace / NOTES_FOLDER
    if not notes.exists():
        return None
    for note in notes.rglob("*.md"):
        try:
            meta, _ = parse_frontmatter(note.read_text(encoding="utf-8"))
        except OSError:
            continue
        if isinstance(meta, dict) and meta.get("source_sha256") == digest:
            return note
    return None


def find_existing_conversion(
    source: str | Path,
    workspace: str | Path | None = None,
) -> tuple[str, Path | None]:
    """Return source digest and an existing converted note when available."""
    digest = source_sha256(source)
    ws_value = workspace or config.workspace_path
    if not ws_value:
        return digest, None
    ws = Path(ws_value)
    with _STATE_LOCK:
        state = _load_unlocked(ws)
        entry = state["sources"].get(digest)
    if isinstance(entry, dict):
        raw_path = str(entry.get("output") or "").strip()
        if raw_path:
            output = Path(raw_path)
            if not output.is_absolute():
                output = ws / output
            if output.is_file():
                return digest, output
    return digest, _find_note_by_hash(ws, digest)


def record_conversion(
    digest: str,
    output: str | Path,
    source: str | Path,
    workspace: str | Path | None = None,
) -> None:
    ws_value = workspace or config.workspace_path
    if not ws_value:
        return
    ws = Path(ws_value)
    with _STATE_LOCK:
        state = _load_unlocked(ws)
        state["sources"][digest] = {
            "output": _workspace_rel(Path(output), ws),
            "source_name": Path(source).name,
        }
        path = _state_path(ws)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
