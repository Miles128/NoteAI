"""Reliability and security regression tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sidecar.agent_runner import execute_tool
from sidecar.handlers.agent_handler import AgentHandler
from sidecar.handlers.files_handler import FilesHandler
from sidecar.handlers.ingest_handler import IngestHandler
from sidecar.ingest_pipeline import save_ingest_state
from sidecar.rag.index import filter_usable_chunks, is_usable_chunk

from config import config


def test_is_usable_chunk_requires_body() -> None:
    assert is_usable_chunk({"content": "hello"}) is True
    assert is_usable_chunk({"content": "  "}) is False
    assert is_usable_chunk({}) is False


def test_filter_usable_chunks_drops_empty() -> None:
    hits = [
        {"id": "a", "content": "text"},
        {"id": "b", "content": ""},
        {"id": "c", "content": "   "},
    ]
    filtered = filter_usable_chunks(hits)
    assert [h["id"] for h in filtered] == ["a"]


def test_agent_rejects_unknown_tool() -> None:
    result = execute_tool("run_shell", {"cmd": "rm -rf /"})
    assert result["success"] is False
    assert "还不会这个操作" in result["message"]


def test_agent_chat_rejects_empty_question() -> None:
    srv = SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None))
    handler = AgentHandler(srv)
    result = handler._agent_chat({"question": "   "})
    assert result["success"] is False


def test_rag_chat_with_actions_delegates_without_code_exec() -> None:
    import inspect

    from sidecar.handlers import rag_handler

    source = inspect.getsource(rag_handler.RagHandler._rag_chat_with_actions)
    assert "return self._rag_chat" in source
    assert "exec(" not in source
    assert "eval(" not in source


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes").mkdir(parents=True)
    config.workspace_path = str(d)
    return d


def test_create_note_writes_file(workspace: Path) -> None:
    srv = SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None))
    handler = FilesHandler(srv)
    res = handler._create_note({"title": "可靠笔记", "topic": ""})
    assert res["success"] is True
    path = workspace / res["path"]
    assert path.exists()
    assert "可靠笔记" in path.read_text(encoding="utf-8")


def test_get_ingest_status_includes_progress(workspace: Path) -> None:
    save_ingest_state(
        {
            "status": "interrupted",
            "stage": "index",
            "progress": 0.42,
            "message": "索引中",
            "stats": {},
        }
    )
    srv = SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None))
    handler = IngestHandler(srv)
    status = handler._get_ingest_status({})
    assert status["needs_resume"] is True
    assert status["progress"] == 0.42
    assert status["stage"] == "index"


def test_run_kb_lint_detects_broken_link(workspace: Path) -> None:
    from sidecar.kb_lint import run_kb_lint

    (workspace / "schema.md").write_text(
        "ai_may_edit_wiki: true\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    note = workspace / "Notes" / "x.md"
    note.write_text("---\ntopic: AI > 测试\n---\n\n[[missing]]\n", encoding="utf-8")

    with patch("sidecar.kb_lint.auto_refresh_stale_surveys", return_value={"updated": 0, "topics": []}):
        report = run_kb_lint(str(workspace), auto_repair=False)

    assert report["summary"]["broken_link"] >= 1


def test_retrieve_filters_empty_before_expand(workspace: Path) -> None:
    from sidecar.rag.retriever import retrieve

    empty_hits = [
        {"id": "1", "content": "", "file_path": "Notes/a.md", "score": 0.9},
        {"id": "2", "content": "  ", "file_path": "Notes/b.md", "score": 0.8},
    ]
    with (
        patch("sidecar.rag.embedder.encode_query", return_value={"dense_vec": [0.1] * 512}),
        patch("sidecar.rag.index.hybrid_search", return_value=empty_hits),
        patch("sidecar.rag.context_expand.expand_retrieval_context", side_effect=lambda hits, **kw: hits),
    ):
        results = retrieve("test query")
    assert results == []
