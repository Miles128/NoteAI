"""Track compiled note mtimes so ingest skips unchanged files."""

from __future__ import annotations

import json
from pathlib import Path

from config import config
from config.settings import WORKSPACE_APP_FOLDER


def _state_path(workspace: str | None = None) -> Path | None:
    ws = workspace or config.workspace_path
    if not ws:
        return None
    p = Path(ws) / WORKSPACE_APP_FOLDER / "compile_state.json"
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
    path = _state_path(workspace)
    if not path:
        return
    path.write_text(
        json.dumps({"files": files}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def file_needs_compile(rel_path: str, mtime: float, workspace: str | None = None) -> bool:
    state = load_state(workspace)
    prev = state.get(rel_path)
    return prev is None or abs(prev - mtime) > 0.5


def mark_compiled(rel_path: str, mtime: float, workspace: str | None = None) -> None:
    state = load_state(workspace)
    state[rel_path] = mtime
    save_state(state, workspace)
