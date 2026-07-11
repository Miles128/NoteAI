from types import SimpleNamespace

import pytest
from sidecar.handlers.rag_handler import RagHandler

from config import config


def test_finish_chat_does_not_write_rag_memory(monkeypatch, tmp_path) -> None:
    config.workspace_path = str(tmp_path)
    events = []
    handler = RagHandler(
        SimpleNamespace(
            _ctx=SimpleNamespace(config=config, logger=None),
            _send_response=lambda resp: events.append(resp),
        )
    )

    import sidecar.rag.memory as memory

    monkeypatch.setattr(memory, "save_short_memory", lambda *_args, **_kwargs: pytest.fail("memory write called"))
    monkeypatch.setattr(memory, "update_long_memory", lambda *_args, **_kwargs: pytest.fail("memory write called"))

    result = handler._finish_chat("问题", "回答", citations=[])

    assert result["success"] is True
    assert events[-1]["result"]["type"] == "rag_chat_done"
    assert events[-1]["result"]["citation_quality"]["level"] == "none"


def test_finish_chat_includes_citation_quality(tmp_path) -> None:
    config.workspace_path = str(tmp_path)
    events = []
    handler = RagHandler(
        SimpleNamespace(
            _ctx=SimpleNamespace(config=config, logger=None),
            _send_response=lambda resp: events.append(resp),
        )
    )

    result = handler._finish_chat(
        "问题",
        "回答",
        citations=[
            {"file_path": "Notes/a.md", "score": 0.91},
            {"file_path": "Notes/b.md", "score": 0.71},
        ],
    )

    assert result["success"] is True
    payload = events[-1]["result"]
    assert payload["citation_quality"]["level"] == "focused"
    assert payload["citation_quality"]["source_count"] == 2


def test_unscored_current_context_is_not_high_confidence(tmp_path) -> None:
    config.workspace_path = str(tmp_path)
    events = []
    handler = RagHandler(
        SimpleNamespace(
            _ctx=SimpleNamespace(config=config, logger=None),
            _send_response=lambda resp: events.append(resp),
        )
    )

    handler._finish_chat("问题", "回答", citations=[{"file_path": "Notes/current.md", "source_type": "current"}])

    assert events[-1]["result"]["citation_quality"] == {"source_count": 0, "level": "none", "top_score": None}
