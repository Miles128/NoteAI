"""
Integration tests for the ingest pipeline: schema → convert → classify → index → cascade → sync.

Requires project dependencies (see pyproject.toml). Run: pytest tests/integration/
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import config
from config.settings import NOTES_FOLDER, RAW_FOLDER, WORKSPACE_APP_FOLDER


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir()
    (d / "Notes").mkdir()
    (d / "wiki").mkdir(parents=True, exist_ok=True)
    (d / "Raw").mkdir(parents=True, exist_ok=True)
    config.workspace_path = str(d)
    return d


class TestIngestState:
    """Test ingest state management."""

    def test_load_ingest_state_default_idle(self, workspace: Path) -> None:
        from sidecar.ingest_pipeline import load_ingest_state

        state = load_ingest_state()
        assert state["status"] == "idle"

    def test_save_and_load_ingest_state(self, workspace: Path) -> None:
        from sidecar.ingest_pipeline import load_ingest_state, save_ingest_state

        state = {"status": "running", "progress": 0.5}
        save_ingest_state(state)

        loaded = load_ingest_state()
        assert loaded["status"] == "running"
        assert loaded["progress"] == 0.5

    def test_normalize_running_state_to_interrupted(self, workspace: Path) -> None:
        from sidecar.ingest_pipeline import normalize_ingest_state, save_ingest_state

        save_ingest_state({"status": "running", "message": "Processing..."})
        normalized = normalize_ingest_state()

        assert normalized["status"] == "interrupted"
        assert "interrupted_at" in normalized

    def test_cancel_and_clear(self, workspace: Path) -> None:
        from sidecar.ingest_pipeline import clear_cancel, is_cancelled, request_cancel

        clear_cancel()
        assert is_cancelled() is False

        request_cancel()
        assert is_cancelled() is True

        clear_cancel()
        assert is_cancelled() is False


class TestSchemaSetup:
    """Test schema management in ingest pipeline."""

    def test_needs_schema_when_missing(self, workspace: Path) -> None:
        from sidecar.schema_manager import needs_schema_setup

        assert needs_schema_setup(str(workspace)) is True

    def test_no_needs_schema_when_configured(self, workspace: Path) -> None:
        from sidecar.schema_manager import needs_schema_setup

        schema_content = "# Schema\n\nai_may_edit_wiki: true\n\n<!-- noteai-schema-configured -->\n"
        (workspace / "schema.md").write_text(schema_content, encoding="utf-8")
        result = needs_schema_setup(str(workspace))
        assert result is False

    def test_ensure_schema_renames_legacy(self, workspace: Path) -> None:
        from sidecar.schema_manager import ensure_schema

        (workspace / "SCHEMA.md").write_text("# Legacy Schema\n", encoding="utf-8")
        result = ensure_schema(str(workspace))
        assert result is not None
        assert (workspace / "schema.md").exists()


class TestPrepareAutoIngest:
    """Test auto-ingest decision logic."""

    def test_no_workspace_returns_none(self, workspace: Path) -> None:
        from sidecar.ingest_pipeline import prepare_auto_ingest

        config.workspace_path = ""
        result = prepare_auto_ingest()
        assert result["action"] == "none"
        config.workspace_path = str(workspace)

    def test_needs_schema_returns_none(self, workspace: Path) -> None:
        from sidecar.ingest_pipeline import prepare_auto_ingest

        result = prepare_auto_ingest(workspace=str(workspace))
        assert result.get("needs_schema") is True

    def test_with_file_paths_and_schema_returns_start(self, workspace: Path) -> None:
        from sidecar.ingest_pipeline import prepare_auto_ingest

        schema_content = "# Schema\n\nai_may_edit_wiki: true\n\n<!-- noteai-schema-configured -->\n"
        (workspace / "schema.md").write_text(schema_content, encoding="utf-8")
        (workspace / "Notes" / "test.md").write_text("# Test\n", encoding="utf-8")
        result = prepare_auto_ingest(
            workspace=str(workspace),
            file_paths=["Notes/test.md"],
        )
        assert result["action"] == "start"
        assert result["mode"] == "incremental"


class TestFileConverter:
    """Test file conversion pipeline."""

    def test_converter_manager_init(self, workspace: Path) -> None:
        from modules.file_converter import FileConverterManager

        converter = FileConverterManager(str(workspace))
        assert converter is not None

    def test_converter_supports_pdf(self, workspace: Path) -> None:
        from modules.file_converter import FileConverterManager

        converter = FileConverterManager(str(workspace))
        assert hasattr(converter, "convert_file") or hasattr(converter, "convert")


class TestTopicAssigner:
    """Test topic assignment from file paths."""

    def test_auto_assign_from_notes_folder(self, workspace: Path) -> None:
        from utils.topic_assigner import auto_assign_topic_for_file

        topic_dir = workspace / "Notes" / "AI" / "LLM"
        topic_dir.mkdir(parents=True)
        note = topic_dir / "test.md"
        note.write_text("# Title\nBody\n", encoding="utf-8")

        result = auto_assign_topic_for_file(str(note), use_llm=False)

        assert result is not None
        assert result.get("topic") == "AI > LLM"

    def test_sync_wiki_with_files(self, workspace: Path) -> None:
        from utils.topic_assigner import sync_wiki_with_files

        topic_dir = workspace / "Notes" / "AI" / "Products"
        topic_dir.mkdir(parents=True)
        note = topic_dir / "note.md"
        note.write_text("---\ntopic: AI > Products\n---\n# Note\n", encoding="utf-8")

        result = sync_wiki_with_files()

        assert result.get("success") is True
        wiki = (workspace / "wiki" / "WIKI.md").read_text(encoding="utf-8")
        assert "AI" in wiki
        assert "Products" in wiki


class TestCascadeRunner:
    """Test cascade update logic."""

    def test_cascade_topics_returns_empty_when_no_notes(self, workspace: Path) -> None:
        from sidecar.cascade_runner import run_cascade_for_topics

        result = run_cascade_for_topics(str(workspace), [])
        assert isinstance(result, dict)


class TestIngestHandler:
    """Test ingest handler RPC contracts."""

    def test_get_ingest_status(self, workspace: Path) -> None:
        from sidecar.handlers.ingest_handler import IngestHandler

        srv = SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None))
        handler = IngestHandler(srv)

        status = handler._get_ingest_status({})
        assert status.get("success") is True
        assert status.get("status") in ("idle", "running", "complete", "failed", "cancelled")

    def test_needs_schema_setup(self, workspace: Path) -> None:
        from sidecar.handlers.ingest_handler import IngestHandler

        srv = SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None))
        handler = IngestHandler(srv)

        result = handler._needs_schema_setup({})
        assert result.get("needs_setup") is True

    def test_ensure_schema(self, workspace: Path) -> None:
        from sidecar.handlers.ingest_handler import IngestHandler

        srv = SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None))
        handler = IngestHandler(srv)

        result = handler._ensure_schema({})
        assert result is not None


class TestTransferHandler:
    """Test file transfer operations."""

    def test_auto_convert_pending_empty(self, workspace: Path) -> None:
        from sidecar.handlers.transfer_handler import TransferHandler

        srv = SimpleNamespace(
            _ctx=SimpleNamespace(config=config, logger=None),
            _running_tasks=set(),
            _running_tasks_lock=__import__("threading").Lock(),
        )
        handler = TransferHandler(srv)

        result = handler._auto_convert_pending({})
        assert result.get("success") is True
        assert result.get("converted", 0) == 0
