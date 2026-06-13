from pathlib import Path

import pytest
from sidecar.archive_wiki import archive_chat_answer, parse_save_suggestion

from config import config

_SCHEMA_OK = (
    "ai_may_edit_wiki: true\n"
    "ai_may_edit_notes: true\n"
    "<!-- noteai-schema-version: 2 -->\n"
    "<!-- noteai-schema-configured -->\n"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes" / "AI" / "基础").mkdir(parents=True)
    (d / "wiki").mkdir()
    (d / "schema.md").write_text(_SCHEMA_OK, encoding="utf-8")
    config.workspace_path = str(d)
    return d


def test_parse_save_suggestion_yes():
    text = "这是整合后的洞见。\n【存档建议】是"
    clean, suggest = parse_save_suggestion(text)
    assert suggest is True
    assert "存档建议" not in clean
    assert "洞见" in clean


def test_parse_save_suggestion_no():
    text = "根据笔记复述。\n【存档建议】否"
    clean, suggest = parse_save_suggestion(text)
    assert suggest is False
    assert "存档建议" not in clean


def test_parse_save_suggestion_missing_marker():
    clean, suggest = parse_save_suggestion("仅普通回答")
    assert suggest is False
    assert clean == "仅普通回答"


def test_archive_chat_answer_to_notes(workspace: Path) -> None:
    result = archive_chat_answer("问题?", "回答内容", title="测试")
    assert result["success"] is True
    assert result["target"] == "note"
    saved = list((workspace / "Notes" / "小忆对话").glob("*.md"))
    assert len(saved) == 1
    text = saved[0].read_text(encoding="utf-8")
    assert "问题?" in text
    assert "回答内容" in text


def test_archive_chat_answer_to_wiki_with_topic_from_context(workspace: Path) -> None:
    note = workspace / "Notes" / "AI" / "基础" / "示例.md"
    note.write_text("---\ntopic: AI > 基础\n---\n\nbody", encoding="utf-8")
    result = archive_chat_answer(
        "问题?",
        "wiki 回答",
        target="wiki",
        context_file="Notes/AI/基础/示例.md",
    )
    assert result["success"] is True
    assert result["target"] == "wiki"
    saved = list((workspace / "wiki" / "小忆对话").glob("*.md"))
    assert len(saved) == 1
    assert 'topic: "AI > 基础"' in saved[0].read_text(encoding="utf-8")
