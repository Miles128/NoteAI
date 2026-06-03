"""Unified workspace log at wiki/log.md (Karpathy-style, grep-friendly)."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

from config import config
from config.settings import WORKSPACE_APP_FOLDER

_LOCK = threading.Lock()
_LOG_REL = Path("wiki") / "log.md"
_LEGACY_JSON = Path(WORKSPACE_APP_FOLDER) / "activity_log.json"
_LEGACY_MD = Path(WORKSPACE_APP_FOLDER) / "log.md"
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


def _legacy_json_path(workspace: str | None = None) -> Path | None:
    ws = workspace or config.workspace_path
    if not ws:
        return None
    return Path(ws) / _LEGACY_JSON


def _legacy_md_path(workspace: str | None = None) -> Path | None:
    ws = workspace or config.workspace_path
    if not ws:
        return None
    return Path(ws) / _LEGACY_MD


def _parse_legacy_json_entries(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ts = item.get("ts")
        try:
            dt = datetime.fromtimestamp(float(ts))
        except (TypeError, ValueError, OSError):
            dt = datetime.now()
        out.append({
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M:%S"),
            "type": str(item.get("type") or "event").lower(),
            "msg": str(item.get("msg") or "").strip(),
            "detail": str(item.get("detail") or "").strip(),
        })
    return out


def _parse_legacy_md_entries(path: Path) -> list[dict]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[dict] = []
    for raw in content.splitlines():
        stripped = raw.strip()
        if not stripped.startswith("- "):
            continue
        m = re.match(
            r"^-\s+`(?P<time>[^`]+)`\s+(?:\*\*(?P<type>[A-Z_]+)\*\*\s+)?(?P<msg>.+)$",
            stripped,
        )
        if not m:
            continue
        ts_raw = m.group("time").strip()
        date = datetime.now().strftime("%Y-%m-%d")
        time_part = ts_raw
        if " " in ts_raw:
            date, _, time_part = ts_raw.partition(" ")
        entries.append({
            "date": date,
            "time": time_part,
            "type": (m.group("type") or "event").lower(),
            "msg": m.group("msg").strip(),
            "detail": "",
        })
    return entries


def _append_parsed_entries(entries: list[dict]) -> int:
    if not entries:
        return 0
    path = log_path()
    if not path:
        return 0
    try:
        content = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        content = ""
    content = _ensure_header(content)
    lines = content.split("\n") if content else []
    added = 0
    for entry in entries:
        day_header = f"## {entry.get('date', datetime.now().strftime('%Y-%m-%d'))}"
        if day_header not in lines:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(day_header)
        type_upper = str(entry.get("type") or "event").upper()
        msg = str(entry.get("msg") or "").strip()
        if not msg:
            continue
        line = f"- `{entry.get('time', '00:00:00')}` **{type_upper}** {msg}"
        detail = str(entry.get("detail") or "").strip()
        if detail:
            line += f" — {detail}"
        lines.append(line)
        added += 1
    if added:
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return added


def migrate_legacy_logs(workspace: str | None = None) -> dict:
    """Merge legacy `.noteai/activity_log.json` and `.noteai/log.md` into wiki/log.md."""
    ws = workspace or config.workspace_path
    if not ws:
        return {"success": False, "migrated": 0}

    migrated = 0
    json_path = _legacy_json_path(ws)
    if json_path and json_path.exists():
        migrated += _append_parsed_entries(_parse_legacy_json_entries(json_path))
        try:
            json_path.rename(json_path.with_suffix(".json.migrated"))
        except OSError:
            pass

    md_path = _legacy_md_path(ws)
    wiki_log = log_path(ws)
    if md_path and md_path.exists() and wiki_log and md_path.resolve() != wiki_log.resolve():
        migrated += _append_parsed_entries(_parse_legacy_md_entries(md_path))
        try:
            md_path.rename(md_path.with_name("log.md.migrated"))
        except OSError:
            pass

    return {"success": True, "migrated": migrated}
