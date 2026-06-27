"""CLI agent tool 事件：从 Claude NDJSON 解析并生成结构化 cli_agent_tool 事件。"""

from __future__ import annotations

import json
from typing import Any, Callable

EventEmitter = Callable[[dict[str, Any]], None]


def _tool_result_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


class ToolStreamTracker:
    """跟踪 stream-json 中的 tool_use 块。"""

    def __init__(self) -> None:
        self._by_index: dict[int, dict[str, Any]] = {}
        self._by_id: dict[str, dict[str, Any]] = {}

    def handle_stream_event(self, inner: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        itype = inner.get("type")
        index = inner.get("index")

        if itype == "content_block_start":
            block = inner.get("content_block") or {}
            if block.get("type") != "tool_use":
                return events
            tool_id = str(block.get("id") or "")
            name = str(block.get("name") or "tool")
            entry = {
                "tool_id": tool_id,
                "tool": name,
                "input": block.get("input") if isinstance(block.get("input"), dict) else {},
                "input_parts": [],
            }
            if isinstance(index, int):
                self._by_index[index] = entry
            if tool_id:
                self._by_id[tool_id] = entry
            events.append({"phase": "start", "tool_id": tool_id, "tool": name, "input": entry["input"]})
            return events

        if itype == "content_block_delta" and isinstance(index, int):
            delta = inner.get("delta") or {}
            if delta.get("type") != "input_json_delta":
                return events
            entry = self._by_index.get(index)
            if entry is None:
                return events
            entry["input_parts"].append(str(delta.get("partial_json") or ""))
            return events

        if itype == "content_block_stop" and isinstance(index, int):
            entry = self._by_index.pop(index, None)
            if entry is None:
                return events
            raw = "".join(entry.get("input_parts") or [])
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        entry["input"] = parsed
                except Exception:
                    pass
            tool_id = str(entry.get("tool_id") or "")
            if tool_id:
                self._by_id[tool_id] = entry
            events.append(
                {
                    "phase": "start",
                    "tool_id": tool_id,
                    "tool": entry.get("tool"),
                    "input": entry.get("input") or {},
                    "input_ready": True,
                }
            )
        return events

    def lookup(self, tool_id: str) -> dict[str, Any] | None:
        return self._by_id.get(tool_id)


def tool_uses_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in message.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        events.append(
            {
                "phase": "start",
                "tool_id": str(block.get("id") or ""),
                "tool": str(block.get("name") or "tool"),
                "input": block.get("input") if isinstance(block.get("input"), dict) else {},
            }
        )
    return events


def tool_results_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in message.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        tool_id = str(block.get("tool_use_id") or "")
        is_error = bool(block.get("is_error"))
        text = _tool_result_text(block.get("content"))
        events.append(
            {
                "phase": "done",
                "tool_id": tool_id,
                "success": not is_error,
                "result": text[:2000],
            }
        )
    return events


def emit_tool_events(
    agent_id: str,
    payloads: list[dict[str, Any]],
    send_event: EventEmitter | None,
    emit: Callable[[dict[str, Any], EventEmitter | None], None],
) -> None:
    for payload in payloads:
        emit(
            {
                "type": "cli_agent_tool",
                "agent": agent_id,
                **payload,
            },
            send_event,
        )
