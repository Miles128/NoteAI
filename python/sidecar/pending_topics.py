"""Pending topic suggestions persisted under the workspace root."""

import json
from pathlib import Path

from config import config


def get_pending_topics_path() -> Path | None:
    workspace = config.workspace_path
    if not workspace:
        return None
    return Path(workspace) / ".pending_topics.json"


def load_pending_topics() -> list:
    path = get_pending_topics_path()
    if not path or not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_pending_topics(pending: list) -> None:
    path = get_pending_topics_path()
    if not path:
        return
    path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
