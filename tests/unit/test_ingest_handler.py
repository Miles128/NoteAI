from pathlib import Path
from types import SimpleNamespace

import pytest
from sidecar.handlers.ingest_handler import IngestHandler
from sidecar.schema_manager import SCHEMA_FILENAME

from config import config


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


def test_needs_schema_setup_flag(workspace: Path, ingest_handler: IngestHandler) -> None:
    result = ingest_handler._needs_schema_setup({})
    assert result["needs_setup"] is True

    (workspace / SCHEMA_FILENAME).write_text(
        "# s\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    result2 = ingest_handler._needs_schema_setup({})
    assert result2["needs_setup"] is False
