"""Apply and remember high-confidence topic placement decisions."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

from config import config
from config.constants import TOPIC_SEP
from config.settings import NOTES_FOLDER, WORKSPACE_APP_FOLDER
from utils.activity_log import add_entry as _log

_STATE_FILE = "topic_placement_resolutions.json"
_AUTO_MOVE_LOCK = threading.Lock()
_AUTO_MOVE_LAST_RUN: dict[str, float] = {}
_INBOX_AUTO_MOVE_INTERVAL_SECONDS = 30.0


def _state_path(root: Path) -> Path:
    return root / WORKSPACE_APP_FOLDER / _STATE_FILE


def _load_state(root: Path) -> dict:
    try:
        data = json.loads(_state_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(root: Path, data: dict) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _safe_note(root: Path, file_path: str) -> Path:
    path = (root / file_path).resolve()
    path.relative_to((root / NOTES_FOLDER).resolve())
    if path.suffix.lower() != ".md" or not path.is_file():
        raise ValueError("只能处理 Notes/ 下存在的 Markdown 笔记")
    return path


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_placement_kept(
    root: Path,
    file_path: str,
    current_topic: str,
    suggested_topic: str,
) -> bool:
    """Return true while a user's keep decision still matches unchanged content."""
    try:
        note = _safe_note(root, file_path)
        entry = _load_state(root).get(str(note.relative_to(root)))
        return bool(
            isinstance(entry, dict)
            and entry.get("current_topic") == current_topic
            and entry.get("suggested_topic") == suggested_topic
            and entry.get("file_hash") == _file_hash(note)
        )
    except (OSError, ValueError):
        return False


def keep_note_in_current_topic(
    workspace: str | Path,
    file_path: str,
    current_topic: str,
    suggested_topic: str,
) -> dict:
    root = Path(workspace).resolve()
    note = _safe_note(root, file_path)
    current = current_topic.strip()
    suggested = suggested_topic.strip()
    if not current or not suggested or current == suggested:
        return {"success": False, "message": "主题参数无效"}
    topic_parts = note.relative_to(root / NOTES_FOLDER).parts[:-1]
    actual_topic = TOPIC_SEP.join(topic_parts[:3]).strip()
    if actual_topic != current:
        return {"success": False, "message": "笔记当前主题已变化，请刷新后重试"}

    rel = str(note.relative_to(root))
    data = _load_state(root)
    data[rel] = {
        "current_topic": current,
        "suggested_topic": suggested,
        "file_hash": _file_hash(note),
    }
    _save_state(root, data)
    _log("topic_keep", f"保留主题「{current}」→ {note.name}", note.name)
    return {"success": True, "message": f"已保留在「{current}」"}


def auto_move_misplaced_notes(workspace: str | Path) -> dict:
    """Move audit findings whose similarity meets the user's configured threshold."""
    root_key = str(Path(workspace).resolve())
    with _AUTO_MOVE_LOCK:
        _AUTO_MOVE_LAST_RUN[root_key] = time.monotonic()
        return _auto_move_misplaced_notes_locked(workspace)


def auto_move_misplaced_notes_if_due(
    workspace: str | Path,
    interval_seconds: float = _INBOX_AUTO_MOVE_INTERVAL_SECONDS,
) -> dict:
    """Run the Inbox placement pass once per short refresh window."""
    root_key = str(Path(workspace).resolve())
    now = time.monotonic()
    with _AUTO_MOVE_LOCK:
        elapsed = now - _AUTO_MOVE_LAST_RUN.get(root_key, float("-inf"))
        if elapsed < max(0.0, interval_seconds):
            return {
                "success": True,
                "moved": [],
                "errors": [],
                "skipped": "recently_checked",
            }
        _AUTO_MOVE_LAST_RUN[root_key] = now
        return _auto_move_misplaced_notes_locked(workspace)


def _auto_move_misplaced_notes_locked(workspace: str | Path) -> dict:
    """Run one serialized placement pass for Inbox and ingest callers."""
    root = Path(workspace).resolve()
    if not config.auto_topic:
        return {"success": True, "moved": [], "skipped": "auto_topic_disabled"}

    from sidecar.organization_audit import find_misplaced_notes
    from utils.topic_assigner import move_file_to_notes_topic_folder, write_topic_to_file

    threshold = min(1.0, max(0.0, float(config.topic_auto_assign_threshold)))
    moved: list[dict] = []
    errors: list[dict] = []
    for finding in find_misplaced_notes(root):
        score = float(finding.get("suggested_score") or 0.0)
        if score < threshold:
            continue
        rel = str(finding.get("file_path") or "")
        current = str(finding.get("current_topic") or "").strip()
        suggested = str(finding.get("suggested_topic") or "").strip()
        try:
            note = _safe_note(root, rel)
            write_result = write_topic_to_file(str(note), suggested)
            if not write_result.get("success"):
                raise RuntimeError(write_result.get("message") or "写入主题失败")
            move_result = move_file_to_notes_topic_folder(str(note), suggested)
            if not move_result.get("success"):
                write_topic_to_file(str(note), current)
                raise RuntimeError(move_result.get("message") or "移动文件失败")
            row = {
                **finding,
                "new_path": move_result.get("new_path", ""),
            }
            moved.append(row)
            _log(
                "topic_auto_move",
                f"相似度 {score:.0%} ≥ 阈值 {threshold:.0%}，自动移至「{suggested}」→ {note.name}",
                note.name,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append({"file_path": rel, "message": str(exc)})

    if moved:
        from sidecar.wiki_utils import sync_wiki_with_files

        sync_wiki_with_files()
    return {"success": not errors, "threshold": threshold, "moved": moved, "errors": errors}
