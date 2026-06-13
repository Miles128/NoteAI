"""Unit tests for RAG context expansion (surveys + confirmed backlinks)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sidecar.rag.context_expand import expand_retrieval_context

from config import config


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "Notes").mkdir(parents=True)
    (ws / "wiki").mkdir(parents=True)
    config.workspace_path = str(ws)
    return ws


def test_expand_adds_survey_and_backlink(workspace: Path) -> None:
    topic = "AI > Agent"
    survey = workspace / "wiki" / "Agent_综述.md"
    survey.write_text("---\ntopic: AI > Agent\n---\n\n# 综述\n\nAgent 总览。", encoding="utf-8")

    note_a = workspace / "Notes" / "a.md"
    note_b = workspace / "Notes" / "b.md"
    note_a.write_text("---\ntopic: AI > Agent\n---\n\n# A\n\nbody a", encoding="utf-8")
    note_b.write_text("---\ntopic: AI > Agent\n---\n\n# B\n\nbody b linked", encoding="utf-8")

    links_path = workspace / ".links.json"
    links_path.write_text(
        json.dumps(
            {
                "links": [
                    {
                        "from": "Notes/a.md",
                        "to": "Notes/b.md",
                        "status": "confirmed",
                        "reason": "test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    vector_hits = [
        {
            "id": "chunk1",
            "content": "chunk from a",
            "file_path": "Notes/a.md",
            "file_name": "a.md",
            "topic": topic,
            "score": 0.9,
        }
    ]

    expanded = expand_retrieval_context(vector_hits, topics=[topic], workspace=str(workspace))

    types = [r.get("source_type") for r in expanded]
    assert "survey" in types
    assert "vector" in types
    assert "backlink" in types
    backlink = next(r for r in expanded if r.get("source_type") == "backlink")
    assert backlink.get("file_path") == "Notes/b.md"
