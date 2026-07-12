"""Backward-compatible per-file helpers backed by the canonical manifest."""

from __future__ import annotations

from config import config


def load_state(workspace: str | None = None) -> dict[str, float]:
    from sidecar.rag.index import load_manifest

    ws = workspace or config.workspace_path
    if not ws:
        return {}
    return {path: float(entry.get("mtime", 0)) for path, entry in load_manifest(ws).get("files", {}).items()}


def save_state(files: dict[str, float], workspace: str | None = None) -> None:
    # Compatibility no-op: only a successful index rebuild may commit manifest.
    return None


def file_needs_index(rel_path: str, mtime: float, workspace: str | None = None) -> bool:
    state = load_state(workspace)
    prev = state.get(rel_path)
    return prev is None or abs(prev - mtime) > 0.5


def mark_indexed(rel_path: str, mtime: float, workspace: str | None = None) -> None:
    # Compatibility no-op: marking before vector persistence caused false clean
    # states. rebuild_index() now commits the complete manifest atomically.
    return None
