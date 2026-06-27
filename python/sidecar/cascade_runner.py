"""Reliable cascade survey updates with retries, events, and failure persistence."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from config import config
from config.settings import WORKSPACE_APP_FOLDER
from sidecar.cascade import (
    append_changelog,
    collect_topic_notes,
    ensure_topic_folder,
    generate_new_survey,
    get_survey_path,
    update_existing_survey,
)
from sidecar.workspace_rules import load_workspace_rules, resolve_survey_topic
from sidecar.schema_validator import check_wiki_writable
from utils.logger import logger

MAX_RETRIES = 3
RETRY_DELAY_SEC = 2.0


def _failures_path() -> Path | None:
    ws = config.workspace_path
    if not ws:
        return None
    p = Path(ws) / WORKSPACE_APP_FOLDER / "cascade_failures.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_cascade_failures() -> list[dict]:
    path = _failures_path()
    if not path or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_cascade_failures(items: list[dict]) -> None:
    path = _failures_path()
    if not path:
        return
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def record_cascade_failure(topic: str, error: str) -> None:
    items = load_cascade_failures()
    items = [x for x in items if x.get("topic") != topic]
    items.append(
        {
            "topic": topic,
            "error": error,
            "ts": time.time(),
            "retries": MAX_RETRIES,
        }
    )
    save_cascade_failures(items)


def clear_cascade_failure(topic: str) -> None:
    items = [x for x in load_cascade_failures() if x.get("topic") != topic]
    save_cascade_failures(items)


def run_cascade_survey_update(
    topic: str,
    send_response: Callable[[dict], None] | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> dict:
    """Update or create survey for *topic*; emit cascade_* events when send_response set."""
    if not topic or not config.workspace_path:
        return {"success": False, "message": "未设置工作区或主题为空"}

    rules = load_workspace_rules()
    if not rules.get("auto_update_survey", True):
        return {"success": True, "message": "已关闭自动更新综述", "skipped": True}

    topic = resolve_survey_topic(topic, rules.get("survey_at_level", 2))

    ok, msg = check_wiki_writable("更新主题综述")
    if not ok:
        _emit_done(send_response, topic, False, msg)
        return {"success": False, "message": msg}

    def chunk_cb(token: str) -> None:
        if on_chunk:
            on_chunk(token)
        if send_response:
            send_response(
                {
                    "id": "event",
                    "result": {
                        "type": "cascade_survey_chunk",
                        "topic": topic,
                        "token": token,
                    },
                }
            )

    last_error = ""
    result: dict = {"success": False, "message": "未执行"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            folder_result = ensure_topic_folder(topic)
            if not folder_result.get("success"):
                last_error = folder_result.get("message", "主题文件夹创建失败")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SEC)
                    continue
                break

            notes = collect_topic_notes(topic)
            if not notes:
                append_changelog(f"主题「{topic}」暂无笔记，跳过综述更新")
                result = {"success": True, "message": "无笔记，已跳过", "skipped": True}
                clear_cascade_failure(topic)
                break

            survey_path = get_survey_path(topic)
            exists = survey_path and survey_path.exists()
            if exists:
                result = update_existing_survey(topic, notes, on_chunk=chunk_cb)
            else:
                result = generate_new_survey(topic, notes, on_chunk=chunk_cb)

            if result.get("success"):
                append_changelog(f"自动更新主题综述: {topic}")
                clear_cascade_failure(topic)
                break
            last_error = result.get("message", "综述更新失败")
        except Exception as e:
            last_error = str(e)
            logger.error(f"[cascade_runner] attempt {attempt} failed for {topic}: {e}")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SEC)

    if not result.get("success") and not result.get("skipped"):
        result = {"success": False, "message": last_error or "综述更新失败"}
        record_cascade_failure(topic, result["message"])

    _emit_done(send_response, topic, result.get("success", False), result.get("message", ""), result)
    return result


def run_cascade_for_topics(
    topics: list[str],
    send_response: Callable[[dict], None] | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict:
    unique = []
    seen: set[str] = set()
    for t in topics:
        t = (t or "").strip()
        if t and t not in seen:
            seen.add(t)
            unique.append(t)

    ok = 0
    failed: list[str] = []
    total = len(unique)
    for i, topic in enumerate(unique):
        if cancel_check and cancel_check():
            break
        if progress_cb:
            progress_cb(i + 1, total, f"级联综述 ({i + 1}/{total}): {topic}")
        r = run_cascade_survey_update(topic, send_response=send_response)
        if r.get("success"):
            ok += 1
        else:
            failed.append(topic)

    return {"success": not failed, "updated": ok, "failed": failed, "total": total}


def retry_failed_cascades(
    send_response: Callable[[dict], None] | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict:
    topics = [x["topic"] for x in load_cascade_failures() if x.get("topic")]
    if not topics:
        return {"success": True, "updated": 0, "failed": [], "message": "无失败项"}
    return run_cascade_for_topics(topics, send_response=send_response, progress_cb=progress_cb)


def _emit_done(
    send_response: Callable[[dict], None] | None,
    topic: str,
    success: bool,
    message: str,
    data: dict | None = None,
) -> None:
    if not send_response:
        return
    payload = dict(data or {})
    payload.setdefault("success", success)
    payload.setdefault("message", message)
    send_response(
        {
            "id": "event",
            "result": {
                "type": "cascade_done",
                "topic": topic,
                "data": payload,
            },
        }
    )
