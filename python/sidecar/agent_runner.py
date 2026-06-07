"""Structured Agent loop — safe predefined tools, no code execution."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from config import config
from config.constants import TOPIC_SEP
from prompts import (
    AGENT_SYSTEM_PROMPT,
    AGENT_TOOL_RESULT_PROMPT,
    ASSISTANT_READONLY_PROMPT,
    ASSISTANT_READONLY_TOOL_RESULT_PROMPT,
)
from utils.logger import logger

MAX_AGENT_STEPS = 5
MAX_READONLY_PREFETCH_STEPS = 3

READONLY_TOOLS = frozenset({"search_files", "list_topics"})
WRITE_TOOLS = frozenset({"move_file_to_topic", "run_survey", "start_ingest", "create_topic"})


def _file_title(path: str) -> str:
    name = (path or "").strip()
    if not name:
        return "这篇笔记"
    return Path(name).stem or name


def _user_specified_text(text: str, phrase: str) -> bool:
    phrase = (phrase or "").strip()
    if not phrase:
        return False
    return phrase.lower() in (text or "").lower()


def format_tool_status(
    tool_name: str,
    args: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    *,
    phase: str = "done",
) -> str:
    """User-facing plain-language status for Agent tool calls."""
    args = args or {}
    result = result or {}

    if phase == "start":
        if tool_name == "search_files":
            query = (args.get("query") or "").strip() or "相关内容"
            topic = (args.get("topic") or "").strip()
            if topic:
                return f"正在「{topic}」里搜索「{query}」"
            return f"正在笔记里搜索「{query}」"
        if tool_name == "list_topics":
            return "正在查看你的主题分类"
        if tool_name == "create_topic":
            name = (args.get("name") or "").strip()
            parent = (args.get("parent") or "").strip()
            if parent:
                return f"正在创建二级主题「{parent} > {name}」"
            return f"正在创建一级主题「{name}」"
        if tool_name == "move_file_to_topic":
            title = _file_title(str(args.get("file_path") or ""))
            topic = (args.get("topic") or "").strip() or "指定主题"
            return f"正在把《{title}》移到「{topic}」"
        if tool_name == "run_survey":
            topic = (args.get("topic") or "").strip() or "该主题"
            return f"正在更新「{topic}」的主题综述"
        if tool_name == "start_ingest":
            return "正在检查是否需要整理知识库"
        return "正在处理你的请求…"

    ok = bool(result.get("success"))
    msg = str(result.get("message") or "").strip()

    if tool_name == "search_files":
        if not ok:
            return msg or "搜索笔记时出了点问题"
        count = int(result.get("count") or 0)
        if count:
            return f"找到了 {count} 篇相关笔记"
        return "没找到匹配的笔记，可以换个关键词试试"

    if tool_name == "list_topics":
        if not ok:
            return msg or "读取主题列表时出了点问题"
        count = int(result.get("count") or 0)
        return f"共有 {count} 个主题"

    if tool_name == "create_topic":
        if ok:
            return msg or "主题已创建"
        return msg or "没能创建主题"

    if tool_name == "move_file_to_topic":
        if ok:
            return msg or "笔记已移到指定主题"
        return msg or "没能移动这篇笔记"

    if tool_name == "run_survey":
        if ok:
            failed = result.get("failed") or []
            if failed:
                return f"综述更新完成，但有 {len(failed)} 个主题还需要处理"
            return "主题综述已更新"
        return msg or "综述没能更新成功"

    if tool_name == "start_ingest":
        if result.get("started"):
            return "已开始整理知识库"
        if msg:
            return msg
        reason = str(result.get("reason") or "").strip()
        if reason == "up_to_date":
            return "知识库已经是最新的，无需重新整理"
        return "暂时不需要重新整理知识库"

    if not ok:
        return msg or "这一步没能完成"
    return msg or "已完成"


def _format_tool_context(tool_log: list[dict[str, Any]]) -> str:
    if not tool_log:
        return ""
    lines = ["【小忆查询结果】"]
    for entry in tool_log:
        tool = entry.get("tool") or ""
        result = entry.get("result") or {}
        if tool == "list_topics" and result.get("topics"):
            topics = result.get("topics") or []
            preview = "、".join(str(t) for t in topics[:20])
            if len(topics) > 20:
                preview += f" 等共 {len(topics)} 个"
            lines.append(f"- 主题列表：{preview}")
        elif tool == "search_files" and result.get("results"):
            hits = result.get("results") or []
            parts = [f"《{h.get('title', h.get('path', ''))}》" for h in hits[:8]]
            lines.append(f"- 搜索命中：{'、'.join(parts)}")
        else:
            lines.append(f"- {format_tool_status(tool, entry.get('args') or {}, result, phase='done')}")
    return "\n".join(lines)


def _parse_agent_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                data = json.loads(m.group(0))
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _tool_search_files(args: dict[str, Any]) -> dict[str, Any]:
    from utils.fulltext_index import fulltext_index
    from sidecar.textutils import parse_frontmatter

    query = (args.get("query") or "").strip()
    topic_filter = (args.get("topic") or "").strip()
    tag_filter = (args.get("tag") or "").strip()
    workspace = config.workspace_path
    if not workspace or not query:
        return {"success": False, "message": "还没设置工作区，或缺少搜索关键词", "results": []}

    ws = Path(workspace)
    raw = fulltext_index.search(query)
    results: list[dict[str, Any]] = []
    for item in raw[:20]:
        try:
            text = (ws / item["path"]).read_text(encoding="utf-8")
        except OSError:
            continue
        fm, _ = parse_frontmatter(text)
        fm = fm or {}
        file_topic = str(fm.get("topic") or "").strip()
        if topic_filter and topic_filter not in file_topic:
            continue
        tags: list[str] = []
        raw_tags = fm.get("tags", [])
        if isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if t]
        elif isinstance(raw_tags, str) and raw_tags.strip():
            tags = [raw_tags.strip()]
        if tag_filter and tag_filter not in tags:
            continue
        results.append({
            "path": item["path"],
            "title": Path(item["path"]).stem,
            "snippet": item.get("snippet", "")[:120],
            "topic": file_topic,
        })
    return {"success": True, "count": len(results), "results": results}


def _tool_list_topics(_args: dict[str, Any]) -> dict[str, Any]:
    from utils.topic_manager import TopicManager

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "还没设置工作区", "topics": []}
    topics = TopicManager.collect_topic_labels(workspace)
    return {"success": True, "count": len(topics), "topics": topics[:50]}


def _tool_create_topic(args: dict[str, Any]) -> dict[str, Any]:
    from sidecar.cascade import ensure_topic_folder
    from sidecar.schema_validator import require_topic
    from sidecar.wiki_utils import create_topic as wiki_create_topic

    name = (args.get("name") or "").strip()
    parent = (args.get("parent") or "").strip()
    user_text = (args.get("_user_text") or "").strip()

    if TOPIC_SEP in name:
        parts = [p.strip() for p in name.split(TOPIC_SEP) if p.strip()]
        if len(parts) == 1:
            name = parts[0]
        elif len(parts) == 2:
            parent, name = parts[0], parts[1]
        else:
            return {"success": False, "message": "最多支持「一级 > 二级」两级主题"}

    if not name:
        return {"success": False, "message": "请提供主题名称"}

    if parent:
        if not _user_specified_text(user_text, parent):
            return {
                "success": False,
                "needs_user_input": True,
                "message": (
                    f"创建二级主题「{name}」前，需要您明确指定所属的一级主题。"
                    "请告诉我放在哪个一级主题下，小忆不会自动猜测。"
                ),
            }
        topic_full = TOPIC_SEP.join([parent, name])
    else:
        topic_full = name

    ok, err = require_topic(topic_full)
    if not ok:
        return {"success": False, "message": err}

    result = wiki_create_topic(topic_full)
    if not result.get("success"):
        return result

    folder_result = ensure_topic_folder(topic_full)
    if not folder_result.get("success"):
        return {
            "success": False,
            "message": folder_result.get("message", "创建主题文件夹失败"),
        }

    return {"success": True, "message": f"主题「{topic_full}」已创建", "topic": topic_full}


def _tool_move_file_to_topic(args: dict[str, Any]) -> dict[str, Any]:
    from utils.topic_file_ops import move_file_to_topic

    file_path = (args.get("file_path") or "").strip()
    topic = (args.get("topic") or "").strip()
    if not file_path or not topic:
        return {"success": False, "message": "需要指定笔记路径和目标主题"}
    return move_file_to_topic(file_path, topic)


def _tool_run_survey(args: dict[str, Any]) -> dict[str, Any]:
    from sidecar.cascade_runner import run_cascade_for_topics

    topic = (args.get("topic") or "").strip()
    if not topic:
        return {"success": False, "message": "需要指定要更新的主题"}
    result = run_cascade_for_topics([topic], send_response=None, progress_cb=None)
    return {"success": True, "updated": result.get("updated", 0), "failed": result.get("failed", [])}


def _tool_start_ingest(args: dict[str, Any]) -> dict[str, Any]:
    from sidecar.ingest_pipeline import prepare_auto_ingest

    plan = prepare_auto_ingest(file_paths=(args.get("file_paths") or None))
    if plan.get("action") != "start":
        return {
            "success": True,
            "message": "知识库已经是最新的，无需重新整理",
            "started": False,
            "reason": plan.get("reason"),
        }
    return {
        "success": True,
        "started": False,
        "message": "整理任务已加入队列，稍后会自动开始",
        "mode": plan.get("mode"),
    }


_TOOLS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "search_files": _tool_search_files,
    "list_topics": _tool_list_topics,
    "create_topic": _tool_create_topic,
    "move_file_to_topic": _tool_move_file_to_topic,
    "run_survey": _tool_run_survey,
    "start_ingest": _tool_start_ingest,
}


def execute_tool(
    name: str,
    args: dict[str, Any] | None,
    *,
    agent_mode: bool = True,
) -> dict[str, Any]:
    if name in WRITE_TOOLS and not agent_mode:
        return {
            "success": False,
            "message": "这类操作需要先在设置 → 小忆助手中开启「助手模式」",
        }
    fn = _TOOLS.get(name)
    if not fn:
        return {"success": False, "message": f"小忆还不会这个操作：{name}"}
    try:
        return fn(args or {})
    except Exception as e:
        logger.warning(f"[agent] tool {name} error: {e}")
        return {"success": False, "message": f"操作失败：{e}"}


def _run_tool_step(
    tool_name: str,
    tool_args: dict[str, Any],
    *,
    agent_mode: bool,
    user_text: str,
    send_event: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    safe_args = dict(tool_args or {})
    safe_args["_user_text"] = user_text

    if send_event:
        send_event({
            "type": "agent_tool",
            "phase": "start",
            "tool": tool_name,
            "message": format_tool_status(tool_name, safe_args, phase="start"),
        })

    result = execute_tool(tool_name, safe_args, agent_mode=agent_mode)

    if send_event:
        send_event({
            "type": "agent_tool",
            "phase": "done",
            "tool": tool_name,
            "message": format_tool_status(tool_name, safe_args, result, phase="done"),
            "result": result,
        })

    return result


def run_readonly_tool_prefetch(
    question: str,
    *,
    send_event: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    """问答模式：在 RAG 回答前运行只读工具，返回可追加到上下文的文本。"""
    from utils.llm_utils import call_llm_raw

    question = (question or "").strip()
    if not question:
        return ""

    messages = ASSISTANT_READONLY_PROMPT.format(question=question)
    tool_log: list[dict[str, Any]] = []

    for _ in range(MAX_READONLY_PREFETCH_STEPS):
        try:
            raw = call_llm_raw(messages, temperature=0.1)
        except Exception as e:
            logger.warning(f"[agent] readonly prefetch error: {e}")
            break

        parsed = _parse_agent_json(raw)
        if not parsed:
            break

        action = parsed.get("action", "answer")
        if action == "answer":
            break

        if action != "tool":
            break

        tool_name = parsed.get("tool", "")
        if tool_name not in READONLY_TOOLS:
            break

        tool_args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        result = _run_tool_step(
            tool_name,
            tool_args,
            agent_mode=False,
            user_text=question,
            send_event=send_event,
        )
        tool_log.append({"tool": tool_name, "args": tool_args, "result": result})

        messages = ASSISTANT_READONLY_TOOL_RESULT_PROMPT.format(
            tool=tool_name,
            result=json.dumps(result, ensure_ascii=False)[:2000],
        )

    return _format_tool_context(tool_log)


def run_agent_chat(
    question: str,
    *,
    history: str = "",
    agent_mode: bool = True,
    send_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    from sidecar.rag.profile import get_profile_summary
    from utils.llm_utils import APIConfigError, call_llm_raw, check_api_config

    question = (question or "").strip()
    if not question:
        return {"success": False, "message": "请先输入问题"}

    if not config.workspace_path:
        return {"success": False, "message": "还没设置工作区，请先打开一个笔记文件夹"}

    try:
        ok, err = check_api_config()
        if not ok:
            return {"success": False, "message": err}
    except APIConfigError as e:
        return {"success": False, "message": str(e)}

    user_text = f"{history}\n{question}".strip()
    profile = get_profile_summary() or "（暂无）"
    messages = AGENT_SYSTEM_PROMPT.format(
        profile=profile,
        history=history or "无",
        question=question,
    )
    tool_log: list[dict[str, Any]] = []

    for step in range(MAX_AGENT_STEPS):
        try:
            raw = call_llm_raw(messages, temperature=0.2)
        except Exception as e:
            return {"success": False, "message": str(e), "tools": tool_log}

        parsed = _parse_agent_json(raw)
        if not parsed:
            return {"success": True, "answer": raw.strip(), "tools": tool_log}

        action = parsed.get("action", "answer")
        if action == "answer":
            text = parsed.get("text") or parsed.get("answer") or raw.strip()
            return {"success": True, "answer": text, "tools": tool_log}

        if action != "tool":
            return {"success": True, "answer": raw.strip(), "tools": tool_log}

        tool_name = parsed.get("tool", "")
        tool_args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        result = _run_tool_step(
            tool_name,
            tool_args,
            agent_mode=agent_mode,
            user_text=user_text,
            send_event=send_event,
        )
        tool_log.append({"tool": tool_name, "args": tool_args, "result": result})

        messages = AGENT_TOOL_RESULT_PROMPT.format(
            tool=tool_name,
            result=json.dumps(result, ensure_ascii=False)[:2000],
        )

    return {
        "success": False,
        "message": "这个问题有点复杂，小忆已经试了很多步。你可以把问题拆小一点再问我。",
        "tools": tool_log,
    }
