from pathlib import Path

import pytest

from config import config
from sidecar.ingest_pipeline import run_ingest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir()
    (d / "Notes").mkdir()
    config.workspace_path = str(d)
    return d


def test_ingest_aborts_when_schema_not_configured(workspace: Path) -> None:
    result = run_ingest(mode="full")
    assert result.get("needs_schema") is True
    assert result["success"] is False
