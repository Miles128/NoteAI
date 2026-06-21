"""Track per-file mtimes so RAG indexing skips unchanged Notes."""

from __future__ import annotations

import json
from pathlib import Path

from config import config
from config.settings import WORKSPACE_APP_FOLDER
from utils.logger import logger


def _state_path(workspace: str | None = None) -> Path | None:
    ws = workspace or config.workspace_path
    if not ws:
        return None
    p = Path(ws) / WORKSPACE_APP_FOLDER / "rag_index_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_state(workspace: str | None = None) -> dict[str, float]:
    path = _state_path(workspace)
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        files = data.get("files", {})
        if isinstance(files, dict):
            return {str(k): float(v) for k, v in files.items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return {}


def save_state(files: dict[str, float], workspace: str | None = None) -> None:
    import os as _os
    import tempfile as _tempfile

    path = _state_path(workspace)
    if not path:
        return
    data = json.dumps({"files": files}, ensure_ascii=False, indent=2)
    try:
        fd, tmp = _tempfile.mkstemp(dir=str(path.parent), prefix=".rag_index_state_")
        try:
            with _os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
        except Exception:
            _os.close(fd)
            raise
        _os.replace(tmp, str(path))
    except Exception as e:
        logger.warning(f"[rag/index_state] save failed: {e}")
        # Fallback to direct write on atomic-write failure.
        path.write_text(data, encoding="utf-8")


def file_needs_index(rel_path: str, mtime: float, workspace: str | None = None) -> bool:
    state = load_state(workspace)
    prev = state.get(rel_path)
    return prev is None or abs(prev - mtime) > 0.5


def mark_indexed(rel_path: str, mtime: float, workspace: str | None = None) -> None:
    state = load_state(workspace)
    state[rel_path] = mtime
    save_state(state, workspace)
