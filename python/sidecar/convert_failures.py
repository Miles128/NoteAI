"""Persistent conversion failure queue (mirrors cascade_failures pattern)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from config import config
from config.settings import WORKSPACE_APP_FOLDER


def _failures_path() -> Path | None:
    ws = config.workspace_path
    if not ws:
        return None
    p = Path(ws) / WORKSPACE_APP_FOLDER / "convert_failures.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_convert_failures() -> list[dict]:
    path = _failures_path()
    if not path or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_convert_failures(items: list[dict]) -> None:
    path = _failures_path()
    if not path:
        return
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def record_convert_failure(file_path: str, error: str) -> None:
    rel = (file_path or "").strip()
    if not rel:
        return
    items = [x for x in load_convert_failures() if x.get("file") != rel]
    items.append(
        {
            "file": rel,
            "error": (error or "转换失败")[:500],
            "ts": time.time(),
        }
    )
    save_convert_failures(items)


def clear_convert_failure(file_path: str) -> None:
    rel = (file_path or "").strip()
    items = [x for x in load_convert_failures() if x.get("file") != rel]
    save_convert_failures(items)


def cleanup_stale_convert_failures() -> int:
    ws = config.workspace_path
    if not ws:
        return 0
    root = Path(ws)
    original = load_convert_failures()
    if not original:
        return 0
    valid = []
    for item in original:
        rel = (item.get("file") or "").strip()
        if not rel:
            continue
        full = root / rel if not Path(rel).is_absolute() else Path(rel)
        if full.exists():
            valid.append(item)
    removed = len(original) - len(valid)
    if removed:
        save_convert_failures(valid)
    return removed


def record_convert_batch_results(results: list[dict]) -> int:
    """Record failed entries from convert_batch result list. Returns failure count."""
    failed = 0
    for item in results or []:
        if not isinstance(item, dict):
            continue
        if item.get("success"):
            src = (item.get("source") or item.get("file") or item.get("path") or "").strip()
            if src:
                clear_convert_failure(src)
            continue
        src = (item.get("source") or item.get("file") or item.get("path") or "").strip()
        if not src:
            continue
        record_convert_failure(src, str(item.get("error") or item.get("message") or "转换失败"))
        failed += 1
    return failed
