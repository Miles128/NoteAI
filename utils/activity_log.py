"""Activity log — writes to unified wiki/log.md via workspace_log."""

from __future__ import annotations

import time
from datetime import datetime

from utils.workspace_log import append_log, parse_log_entries


def add_entry(action_type: str, message: str, detail: str | None = None) -> None:
    """Record an automated action into wiki/log.md."""
    append_log(action_type, message, detail or "")


def get_entries(limit: int = 100) -> list[dict]:
    """Return recent log entries (compatible shape for UI)."""
    rows = parse_log_entries(limit)
    out: list[dict] = []
    for row in rows:
        ts_text = f"{row.get('date', '')} {row.get('time', '')}".strip()
        try:
            ts = datetime.strptime(ts_text, "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            ts = time.time()
        out.append(
            {
                "ts": ts,
                "type": row.get("type", "event"),
                "msg": row.get("msg", ""),
                "detail": row.get("detail", ""),
            }
        )
    return out


def clear_log() -> None:
    from utils.workspace_log import log_path

    p = log_path()
    if p and p.exists():
        p.unlink(missing_ok=True)
