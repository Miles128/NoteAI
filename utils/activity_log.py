"""Activity log for recording automated actions (file conversion, topic/tag assignment, file moves)."""
import json
import time
from pathlib import Path
from config import config

_LOG_DIR = ".noteai"
_LOG_FILE = "activity_log.json"
_MAX_ENTRIES = 200


def _log_path():
    ws = config.workspace_path
    if not ws:
        return None
    p = Path(ws) / _LOG_DIR / _LOG_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def add_entry(action_type, message, detail=None):
    """Record an automated action."""
    p = _log_path()
    if not p:
        return
    entry = {
        "ts": time.time(),
        "type": action_type,
        "msg": message,
        "detail": detail or "",
    }
    try:
        entries = []
        if p.exists():
            entries = json.loads(p.read_text(encoding="utf-8"))
        entries.append(entry)
        if len(entries) > _MAX_ENTRIES:
            entries = entries[-_MAX_ENTRIES:]
        p.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_entries(limit=100):
    """Return recent log entries."""
    p = _log_path()
    if not p or not p.exists():
        return []
    try:
        entries = json.loads(p.read_text(encoding="utf-8"))
        return entries[-limit:]
    except Exception:
        return []


def clear_log():
    p = _log_path()
    if p and p.exists():
        p.unlink(missing_ok=True)
