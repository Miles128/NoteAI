from pathlib import Path
from types import SimpleNamespace

import pytest
from sidecar.handlers.ingest_handler import IngestHandler
from sidecar.ingest_pipeline import save_ingest_state
from sidecar.schema_manager import SCHEMA_FILENAME

from config import config
from tests.workspace_rules_helpers import write_workspace_rules


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir(parents=True, exist_ok=True)
    (d / "Notes").mkdir(parents=True, exist_ok=True)
    config.workspace_path = str(d)
    return d


@pytest.fixture
def ingest_handler() -> IngestHandler:
    server = SimpleNamespace(
        _ctx=SimpleNamespace(config=config, logger=None),
        _send_response=lambda _resp: None,
    )
    return IngestHandler(server)


def test_get_ingest_status_idle(workspace: Path, ingest_handler: IngestHandler) -> None:
    status = ingest_handler._get_ingest_status({})
    assert status["status"] == "idle"


def test_get_ingest_status_does_not_interrupt_running_pipeline(workspace: Path, ingest_handler: IngestHandler) -> None:
    save_ingest_state({"status": "running", "stage": "semantic", "progress": 0.5})

    status = ingest_handler._get_ingest_status({})

    assert status["status"] == "running"
    assert status["running"] is True


def test_ensure_running_respects_auto_ingest_switch(workspace: Path, ingest_handler: IngestHandler) -> None:
    (workspace / SCHEMA_FILENAME).write_text(
        "# s\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    original = config.ingest_auto_enabled
    config.ingest_auto_enabled = False
    try:
        result = ingest_handler.ensure_running(file_paths=["Notes/new.md"])
    finally:
        config.ingest_auto_enabled = original

    assert result["success"] is True
    assert result["started"] is False
    assert result["reason"] == "auto_disabled"


def test_check_ingest_updates_reports_up_to_date(workspace: Path, ingest_handler: IngestHandler) -> None:
    write_workspace_rules(workspace)
    save_ingest_state({"status": "complete", "last_complete_at": 1.0})

    result = ingest_handler._check_ingest_updates({})

    assert result["success"] is True
    assert result["has_updates"] is False
    assert result["action"] == "none"
    assert result["reason"] == "up_to_date"


def test_check_ingest_updates_reports_start_for_file_paths(workspace: Path, ingest_handler: IngestHandler) -> None:
    write_workspace_rules(workspace)

    result = ingest_handler._check_ingest_updates({"file_paths": ["Notes/new.md"]})

    assert result["success"] is True
    assert result["has_updates"] is True
    assert result["action"] == "start"
    assert result["mode"] == "incremental"
    assert result["file_paths"] == ["Notes/new.md"]


def test_retry_cancelled_ingest_resumes_completed_stages(
    workspace: Path, ingest_handler: IngestHandler, monkeypatch
) -> None:
    write_workspace_rules(workspace)
    save_ingest_state(
        {
            "status": "cancelled",
            "mode": "full",
            "file_paths": [],
            "completed_stages": ["rules", "convert"],
        }
    )
    calls: list[tuple] = []
    monkeypatch.setattr(
        ingest_handler._server,
        "_start_task",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
        raising=False,
    )

    result = ingest_handler._retry_ingest({"mode": "full"})

    assert result["success"] is True
    assert result["resume"] is True
    task_args = calls[0][1]["args"]
    assert task_args[0:3] == ("full", [], True)
