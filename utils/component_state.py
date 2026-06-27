"""Persist user opt-out for optional installable components (RAG, cloud, …)."""

from __future__ import annotations

import json
import threading
from typing import Any

from config.settings import SYSTEM_APP_DATA_DIR
from utils.logger import logger

_COMPONENTS_FILE = SYSTEM_APP_DATA_DIR / "components.json"
_lock = threading.Lock()

# Components the user explicitly removed via Settings → Components.
_KNOWN = frozenset({"rag", "cloud_tencent", "cloud_baidu"})


def _load() -> dict[str, Any]:
    if not _COMPONENTS_FILE.exists():
        return {"removed": {}}
    try:
        data = json.loads(_COMPONENTS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("removed"), dict):
            return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[component_state] failed to read %s: %s", _COMPONENTS_FILE, e)
    return {"removed": {}}


def _save(data: dict[str, Any]) -> None:
    _COMPONENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _COMPONENTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_COMPONENTS_FILE)


def is_component_removed(name: str) -> bool:
    """Return True when the user removed *name* from Settings."""
    if name not in _KNOWN:
        return False
    with _lock:
        removed = _load().get("removed", {})
    return bool(removed.get(name))


def set_component_removed(name: str, removed: bool) -> None:
    if name not in _KNOWN:
        raise ValueError(f"unknown component: {name}")
    with _lock:
        data = _load()
        bucket = data.setdefault("removed", {})
        if removed:
            bucket[name] = True
        else:
            bucket.pop(name, None)
        _save(data)


def get_removed_components() -> dict[str, bool]:
    with _lock:
        removed = _load().get("removed", {})
    return {name: bool(removed.get(name)) for name in _KNOWN}
