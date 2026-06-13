from pathlib import Path
from unittest.mock import patch

import pytest
from sidecar.ingest_pipeline import clear_cancel, load_ingest_state, request_cancel, run_ingest
from sidecar.schema_manager import SCHEMA_FILENAME

from config import config


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes").mkdir(parents=True)
    (d / "wiki").mkdir()
    config.workspace_path = str(d)
    return d


def test_run_ingest_creates_schema_and_completes(workspace: Path) -> None:
    (workspace / SCHEMA_FILENAME).write_text(
        "# test\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    events: list[dict] = []
    stages: list[str] = []

    def on_progress(stage: str, progress: float, message: str, extra: dict | None = None) -> None:
        stages.append(stage)

    def on_event(resp: dict) -> None:
        events.append(resp.get("result", {}))

    with (
        patch("sidecar.ingest_pipeline.run_cascade_for_topics", return_value={"updated": 0, "failed": []}),
        patch("sidecar.ingest_pipeline.retry_failed_cascades", return_value={"updated": 0}),
        patch("sidecar.ingest_pipeline.sync_wiki_with_files"),
        patch("utils.note_compiler.compile_notes_batch", return_value=(0, [])),
        patch("sidecar.ingest_pipeline._index_markdown_files", return_value=(0, [])),
    ):
        result = run_ingest(mode="full", send_progress=on_progress, send_event=on_event)

    assert result["success"] is True
    assert "schema" in stages
    assert "sync" in stages
    assert any(e.get("type") == "ingest_complete" for e in events)
    assert load_ingest_state()["status"] == "complete"


def test_run_ingest_respects_cancel(workspace: Path) -> None:
    (workspace / SCHEMA_FILENAME).write_text(
        "# test\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    request_cancel()

    with patch("sidecar.ingest_pipeline.clear_cancel"), patch("sidecar.ingest_pipeline.sync_wiki_with_files"):
        result = run_ingest(mode="full")

    assert result.get("cancelled") is True
    assert load_ingest_state()["status"] == "cancelled"
    clear_cancel()


def test_scan_index_pending_finds_changed_notes(workspace: Path) -> None:
    from sidecar.ingest_pipeline import _scan_index_pending

    md = workspace / "Notes" / "changed.md"
    md.write_text("# hello", encoding="utf-8")
    pending = _scan_index_pending(str(workspace))
    assert md in pending
