from pathlib import Path

import pytest

from config import config
from sidecar.ingest_pipeline import (
    load_ingest_state,
    normalize_ingest_state,
    prepare_auto_ingest,
    request_full_ingest,
    save_ingest_state,
)
from sidecar.schema_manager import SCHEMA_FILENAME


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes").mkdir(parents=True)
    (d / "wiki").mkdir()
    config.workspace_path = str(d)
    return d


def test_normalize_running_becomes_interrupted(workspace: Path) -> None:
    save_ingest_state({"status": "running", "stage": "classify", "message": "分类中"})
    state = normalize_ingest_state()
    assert state["status"] == "interrupted"


def test_prepare_auto_ingest_resumes_interrupted(workspace: Path) -> None:
    (workspace / SCHEMA_FILENAME).write_text(
        "# ok\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    save_ingest_state({
        "status": "interrupted",
        "mode": "full",
        "completed_stages": ["schema", "convert", "compile"],
    })
    plan = prepare_auto_ingest(str(workspace))
    assert plan["action"] == "start"
    assert plan["resume"] is True
    assert plan["mode"] == "full"


def test_prepare_auto_ingest_idle_when_up_to_date(workspace: Path) -> None:
    (workspace / SCHEMA_FILENAME).write_text(
        "# ok\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    save_ingest_state({"status": "complete", "last_complete_at": 1.0})
    plan = prepare_auto_ingest(str(workspace))
    assert plan["action"] == "none"
    assert plan.get("reason") == "up_to_date"


def test_prepare_auto_ingest_with_file_paths(workspace: Path) -> None:
    (workspace / SCHEMA_FILENAME).write_text(
        "# ok\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    plan = prepare_auto_ingest(str(workspace), file_paths=["Notes/new.md"])
    assert plan["action"] == "start"
    assert plan["mode"] == "incremental"
    assert plan["file_paths"] == ["Notes/new.md"]
