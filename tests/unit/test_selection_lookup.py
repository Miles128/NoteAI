from types import SimpleNamespace

from sidecar.handlers.rag_handler import RagHandler

from config import config


def _handler(events: list) -> RagHandler:
    config.workspace_path = "/tmp/workspace"
    return RagHandler(
        SimpleNamespace(
            _ctx=SimpleNamespace(config=config, logger=None),
            _send_response=lambda event: events.append(event),
        )
    )


def test_selection_lookup_streams_quick_answer_then_rag(monkeypatch) -> None:
    events = []
    handler = _handler(events)

    monkeypatch.setattr(
        "utils.llm_utils.call_llm_raw_stream",
        lambda _prompt, **kwargs: (kwargs["chunk_callback"]("快速解释"), "快速解释")[1],
    )
    monkeypatch.setattr(
        handler,
        "_answer_with_rag",
        lambda _params, question, _history, **_kwargs: {"success": True, "question": question},
    )

    result = handler._answer_selection_lookup(
        {"selection_route": "rag", "current_file": "Notes/a.md"},
        "测试术语",
        use_vector_rag=True,
    )

    assert result["success"] is True
    chunks = [event["result"]["token"] for event in events]
    assert chunks == ["快速解释", "\n\n---\n\n### 知识库补充\n\n"]


def test_selection_lookup_routes_web_after_quick_answer(monkeypatch) -> None:
    events = []
    handler = _handler(events)

    monkeypatch.setattr(
        "utils.llm_utils.call_llm_raw_stream",
        lambda _prompt, **kwargs: (kwargs["chunk_callback"]("快速解释"), "快速解释")[1],
    )
    monkeypatch.setattr(
        handler,
        "_answer_without_retrieval",
        lambda _question, _history, *, intent: {"success": intent == "web"},
    )

    result = handler._answer_selection_lookup({"selection_route": "web"}, "最新消息", use_vector_rag=True)

    assert result["success"] is True
    assert events[-1]["result"]["token"] == "\n\n---\n\n### 联网补充\n\n"
