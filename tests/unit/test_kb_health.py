"""KB health metrics for home dashboard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sidecar.ingest_pipeline import load_ingest_state, prepare_auto_ingest, request_full_ingest
from sidecar.kb_health import compute_kb_health
from sidecar.schema_manager import SCHEMA_FILENAME

from config import config
from config.constants import WORKSPACE_APP_FOLDER


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    notes = ws / "Notes" / "AI" / "Agent"
    notes.mkdir(parents=True)
    (notes / "note-a.md").write_text("# A\n", encoding="utf-8")
    (notes / "note-b.md").write_text("# B\n", encoding="utf-8")
    (ws / "wiki").mkdir(parents=True)
    (ws / "wiki" / "Agent_综述.md").write_text("# Survey\n", encoding="utf-8")
    (ws / ".links.json").write_text(
        json.dumps(
            {
                "links": [
                    {"from": "Notes/AI/Agent/note-a.md", "to": "Notes/AI/Agent/note-b.md", "status": "confirmed"},
                ]
            }
        ),
        encoding="utf-8",
    )
    lint_dir = ws / WORKSPACE_APP_FOLDER
    lint_dir.mkdir(parents=True)
    (lint_dir / "lint_report.json").write_text(
        json.dumps({"issues": [{"kind": "broken_link"}], "summary": {"total": 1, "broken_link": 1}}),
        encoding="utf-8",
    )
    config.workspace_path = str(ws)
    return ws


def test_compute_kb_health_metrics(workspace: Path) -> None:
    result = compute_kb_health(str(workspace))
    assert result["success"] is True
    assert result["notes_total"] == 2
    assert result["survey_topics_total"] >= 1
    assert result["survey_topics_with"] >= 1
    assert result["survey_coverage_pct"] > 0
    assert result["outbound_links_total"] == 1
    assert result["avg_outbound_links"] == 0.5
    assert result["lint_total"] == 1


def test_request_full_ingest_marks_next_run(workspace: Path) -> None:
    (workspace / SCHEMA_FILENAME).write_text(
        "# ok\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    request_full_ingest()
    state = load_ingest_state()
    assert state.get("force_full_next") is True

    plan = prepare_auto_ingest(str(workspace))
    assert plan["action"] == "start"
    assert plan["mode"] == "full"
    assert plan.get("force_full") is True
    assert plan["resume"] is False
