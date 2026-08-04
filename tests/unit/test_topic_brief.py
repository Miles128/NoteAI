from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sidecar.handlers.semantic_handler import SemanticHandler
from sidecar.semantic.store import SemanticStore

from config import config


@pytest.fixture
def brief_handler(tmp_path: Path):
    previous = config.workspace_path
    workspace = tmp_path / "workspace"
    (workspace / "Notes").mkdir(parents=True)
    config.workspace_path = str(workspace)
    store = SemanticStore(workspace)
    store.initialize()
    now = datetime.now(timezone.utc)
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO semantic_change_log(id, change_kind, object_kind, object_id,
               label, detail_json, source_path, topic, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "log-1",
                "added",
                "claim",
                "c1",
                "混合检索结合向量与关键词",
                "{}",
                "Notes/AI/RAG.md",
                "AI > RAG",
                (now - timedelta(hours=1)).isoformat(),
            ),
        )
        conn.execute(
            """INSERT INTO semantic_change_log(id, change_kind, object_kind, object_id,
               label, detail_json, source_path, topic, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("log-2", "updated", "entity", "e1", "BM25", "{}", "Notes/AI/RAG.md", "AI > RAG", now.isoformat()),
        )
        conn.execute(
            """INSERT INTO semantic_change_log(id, change_kind, object_kind, object_id,
               label, detail_json, source_path, topic, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "log-3",
                "added",
                "concept",
                "c2",
                "注意力机制",
                "{}",
                "Notes/AI/ML.md",
                "机器学习",
                (now - timedelta(minutes=30)).isoformat(),
            ),
        )
    handler = SemanticHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))
    yield handler
    config.workspace_path = previous


def test_topics_with_changes_returns_topics_newest_first(brief_handler):
    store = brief_handler._store()
    assert store is not None
    topics = store.topics_with_changes(days=7)
    assert topics == ["AI > RAG", "机器学习"]


def test_topic_changes_returns_ordered_rows(brief_handler):
    store = brief_handler._store()
    assert store is not None
    rows = store.topic_changes(topic="AI > RAG", days=7)
    assert [r["change_kind"] for r in rows] == ["updated", "added"]
    assert rows[0]["label"] == "BM25"
    assert rows[0]["source_path"] == "Notes/AI/RAG.md"


def test_get_topic_brief_without_topic_returns_topic_list(brief_handler):
    result = brief_handler._get_topic_brief({"days": 7})
    assert result["success"] is True
    assert result["topics"] == ["AI > RAG", "机器学习"]
    assert result["topic"] == ""


def test_get_topic_brief_no_changes_returns_empty_brief(brief_handler):
    result = brief_handler._get_topic_brief({"topic": "不存在的主题", "days": 7})
    assert result["success"] is True
    assert result["brief"] and "没有语义变化" in result["brief"]
    assert result["fallback"] is False


def test_get_topic_brief_fallback_without_llm(brief_handler, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no llm")

    monkeypatch.setattr("utils.llm_utils.call_llm_raw", boom)
    result = brief_handler._get_topic_brief({"topic": "AI > RAG", "days": 7})
    assert result["success"] is True
    assert result["fallback"] is True
    assert "结构化变化记录" in result["brief"]
    assert "BM25" in result["brief"]


def test_get_topic_brief_uses_llm_when_available(brief_handler, monkeypatch):
    def fake_llm(prompt, **kwargs):
        assert "AI > RAG" in prompt
        return "## 主题简报\n\n过去 7 天该主题新增 2 项变化。"

    monkeypatch.setattr("utils.llm_utils.call_llm_raw", fake_llm)
    result = brief_handler._get_topic_brief({"topic": "AI > RAG", "days": 7})
    assert result["success"] is True
    assert result["fallback"] is False
    assert "新增 2 项变化" in result["brief"]
