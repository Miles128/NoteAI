"""Unified workspace log at wiki/log.md (Karpathy-style, grep-friendly)."""

from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path

from config import config

_LOCK = threading.Lock()
_LOG_REL = Path("wiki") / "log.md"
_MAX_LINES_PER_DAY = 200


def log_path(workspace: str | None = None) -> Path | None:
    ws = workspace or config.workspace_path
    if not ws:
        return None
    p = Path(ws) / _LOG_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _ensure_header(content: str) -> str:
    if content.strip():
        return content
    return (
        "# 知识库变更日志\n\n"
        "> 统一记录：入库、转换、分类、级联、问答归档、Lint。按日分组。\n\n"
    )


def append_log(entry_type: str, message: str, detail: str = "") -> None:
    """Append one line under today's ## date section."""
    with _LOCK:
        path = log_path()
        if not path:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        today = datetime.now().strftime("%Y-%m-%d")
        type_upper = (entry_type or "event").strip().upper()
        line = f"- `{timestamp}` **{type_upper}** {message.strip()}"
        if detail and detail.strip():
            line += f" — {detail.strip()}"

        try:
            content = path.read_text(encoding="utf-8") if path.exists() else ""
        except OSError:
            content = ""

        content = _ensure_header(content)
        day_header = f"## {today}"
        if day_header not in content:
            if not content.endswith("\n"):
                content += "\n"
            content += f"\n{day_header}\n"

        lines = content.split("\n")
        insert_idx = len(lines)
        for i, line_text in enumerate(lines):
            if line_text.strip() == day_header:
                insert_idx = i + 1
                break

        lines.insert(insert_idx, line)
        # trim old lines for this day
        day_start = insert_idx
        day_end = day_start
        while day_end < len(lines) and not (
            day_end > day_start and lines[day_end].startswith("## ")
        ):
            day_end += 1
        day_lines = lines[day_start:day_end]
        if len(day_lines) > _MAX_LINES_PER_DAY:
            lines = lines[:day_start] + day_lines[-_MAX_LINES_PER_DAY :]

        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_log_entries(limit: int = 100, workspace: str | None = None) -> list[dict]:
    path = log_path(workspace)
    if not path or not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []

    entries: list[dict] = []
    current_day = ""
    pattern = re.compile(
        r"^- `(?P<time>\d{2}:\d{2}:\d{2})` \*\*\[?(?P<type>[A-Z_]+)\]?\*\* (?P<msg>.+)$"
    )
    for raw in content.splitlines():
        stripped = raw.strip()
        if stripped.startswith("## "):
            current_day = stripped[3:].strip()
            continue
        m = pattern.match(stripped)
        if not m:
            continue
        msg = m.group("msg")
        detail = ""
        if " — " in msg:
            msg, detail = msg.split(" — ", 1)
        entries.append({
            "date": current_day,
            "time": m.group("time"),
            "type": m.group("type").lower(),
            "msg": msg.strip(),
            "detail": detail.strip(),
        })
    return entries[-limit:]
