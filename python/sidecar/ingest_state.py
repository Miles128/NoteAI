"""Ingest pipeline persistence: state, fingerprint, cancel generation."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

from config import config, is_ignored_dir
from config.settings import RAW_FOLDER, WORKSPACE_APP_FOLDER
from modules.file_converter import FileConverterManager
from utils.logger import logger

_cancel_event = threading.Event()
_cancel_lock = threading.Lock()
_cancel_generation = 0
_state_lock = threading.Lock()


def _state_path() -> Path | None:
    ws = config.workspace_path
    if not ws:
        return None
    p = Path(ws) / WORKSPACE_APP_FOLDER / "ingest_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _fingerprint_path(workspace: str) -> Path:
    p = Path(workspace) / WORKSPACE_APP_FOLDER / "ingest_fingerprint.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_fingerprint(workspace: str) -> dict:
    path = _fingerprint_path(workspace)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_fingerprint(workspace: str, fingerprint: dict) -> None:
    path = _fingerprint_path(workspace)
    try:
        _write_json_atomic(path, fingerprint)
    except OSError as e:
        logger.warning("[ingest] failed to save fingerprint: %s", e)


def _workspace_file_fingerprint(workspace: str) -> dict:
    """Fast fingerprint of tracked files: path -> [mtime, size]."""
    ws = Path(workspace)
    supported = set(FileConverterManager.get_supported_formats())
    fingerprint: dict = {}
    for f in ws.rglob("*"):
        if not f.is_file() or f.name.startswith("."):
            continue
        rel = f.relative_to(ws)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if any(is_ignored_dir(p) for p in rel.parts):
            continue
        if WORKSPACE_APP_FOLDER in rel.parts or "wiki" in rel.parts or RAW_FOLDER in rel.parts:
            continue
        suffix = f.suffix.lower()
        is_md = suffix == ".md"
        is_convertible = suffix in supported
        if not is_md and not is_convertible:
            continue
        try:
            stat = f.stat()
            fingerprint[str(rel).replace("\\", "/")] = [stat.st_mtime, stat.st_size]
        except OSError:
            continue
    return fingerprint


def _workspace_files_changed(workspace: str) -> tuple[bool, dict]:
    """Return (changed, current_fingerprint).

    Uses mtime + size as the change signal. A full hash is computed only when
    mtime/size match but we still want to be safe, which is skipped here for
    speed; callers fall back to content checks when needed.
    """
    current = _workspace_file_fingerprint(workspace)
    previous = _load_fingerprint(workspace)
    if previous == current:
        return False, current
    return True, current


def load_ingest_state() -> dict:
    path = _state_path()
    if not path or not path.exists():
        return {"status": "idle"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"status": "idle"}
    except (OSError, json.JSONDecodeError):
        return {"status": "idle"}


def save_ingest_state(state: dict) -> None:
    path = _state_path()
    if not path:
        return
    with _state_lock:
        _write_json_atomic(path, state)


def _write_json_atomic(path: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def request_cancel() -> None:
    global _cancel_generation
    with _cancel_lock:
        _cancel_generation += 1
        _cancel_event.set()


def clear_cancel() -> None:
    _cancel_event.clear()


def is_cancelled() -> bool:
    return _cancel_event.is_set()


def cancel_generation() -> int:
    with _cancel_lock:
        return _cancel_generation


def normalize_ingest_state() -> dict:
    """Mark orphaned ``running`` state (process killed mid-pipeline) as interrupted."""
    state = load_ingest_state()
    if state.get("status") == "running":
        state["status"] = "interrupted"
        state["interrupted_at"] = time.time()
        msg = (state.get("message") or "").strip()
        if "续跑" not in msg:
            state["message"] = (msg + " — 上次未跑完，将自动续跑").strip(" —")
        save_ingest_state(state)
    return state
