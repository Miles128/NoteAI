from pathlib import Path

import pytest

from config import config
from sidecar.schema_manager import SCHEMA_FILENAME
from sidecar.agent_runner import (
    _parse_agent_json,
    _tool_create_topic,
    execute_tool,
    format_tool_status,
)
from sidecar.multi_source import import_transcript
from utils.link_indexer import discover_cross_refs_for_file, load_links


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    notes = d / "Notes" / "AI" / "子题"
    notes.mkdir(parents=True)
    for i, title in enumerate(["源文章", "同主题A", "同主题B", "提及源", "标签友", "远房亲戚"]):
        p = notes / f"{title}.md"
        topic = "AI > 子题" if i < 3 else "AI > 其他"
        tags = 'tags: [RAG, 测试]' if i == 4 else "tags: []"
        body = f"讨论 {title} 的内容。"
        if i == 3:
            body = "这里提到了源文章的核心观点。"
        p.write_text(f"---\ntopic: {topic}\n{tags}\n---\n\n# {title}\n\n{body}\n", encoding="utf-8")
    (d / "wiki").mkdir(parents=True, exist_ok=True)
    (d / SCHEMA_FILENAME).write_text(
        "# ok\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    config.workspace_path = str(d)
    return d


def test_parse_agent_json() -> None:
    assert _parse_agent_json('{"action":"answer","text":"ok"}')["action"] == "answer"
    wrapped = '```json\n{"action":"tool","tool":"list_topics","args":{}}\n```'
    assert _parse_agent_json(wrapped)["tool"] == "list_topics"


def test_agent_tool_list_topics(workspace: Path) -> None:
    result = execute_tool("list_topics", {})
    assert result["success"] is True
    assert result["count"] >= 1


def test_format_tool_status_plain_language() -> None:
    start = format_tool_status("search_files", {"query": "RAG"}, phase="start")
    assert "搜索" in start
    assert "RAG" in start

    done = format_tool_status(
        "search_files",
        {"query": "RAG"},
        {"success": True, "count": 3},
        phase="done",
    )
    assert "3" in done
    assert "篇" in done


def test_write_tool_blocked_without_agent_mode() -> None:
    result = execute_tool("create_topic", {"name": "测试"}, agent_mode=False)
    assert result["success"] is False
    assert "助手模式" in result["message"]


def test_create_topic_l2_requires_user_specified_parent(workspace: Path) -> None:
    denied = _tool_create_topic({
        "name": "子主题",
        "parent": "AI Agent",
        "_user_text": "帮我建个子主题",
    })
    assert denied["success"] is False
    assert denied.get("needs_user_input") is True

    allowed = _tool_create_topic({
        "name": "子主题",
        "parent": "AI Agent",
        "_user_text": "在 AI Agent 下创建子主题",
    })
    assert allowed["success"] is True
    assert allowed.get("topic") == "AI Agent > 子主题"


def test_create_topic_l1_without_parent(workspace: Path) -> None:
    result = _tool_create_topic({"name": "新领域", "_user_text": "新建一级主题 新领域"})
    assert result["success"] is True
    assert result.get("topic") == "新领域"


def test_discover_cross_refs_finds_related(workspace: Path) -> None:
    rel = "Notes/AI/子题/源文章.md"
    result = discover_cross_refs_for_file(rel, max_links=8, use_llm=False)
    assert result["success"] is True
    assert result["added"] >= 1
    links = load_links().get("links", [])
    outgoing = [l for l in links if l.get("from") == rel]
    assert len(outgoing) >= 1


def test_import_transcript(workspace: Path) -> None:
    tr = import_transcript("会议记录", "说话内容", source="Zoom")
    assert tr["success"] is True
    assert tr["path"].endswith(".md")


def test_create_note(workspace: Path) -> None:
    from types import SimpleNamespace

    from config import config as app_config
    from sidecar.handlers.files_handler import FilesHandler

    app_config.workspace_path = str(workspace)
    srv = SimpleNamespace(_ctx=SimpleNamespace(config=app_config, logger=None))
    h = FilesHandler(srv)
    res = h._create_note({"title": "测试笔记", "topic": ""})
    assert res["success"] is True
    assert "Notes/_未分类" in res["path"]
