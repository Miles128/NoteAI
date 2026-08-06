import json
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

    assert events[-1]["result"]["citation_quality"] == {"source_count": 1, "level": "weak", "top_score": None}


def test_cited_sources_keeps_only_valid_references_in_answer() -> None:
    citations = [
        {"index": 1, "file_path": "Notes/a.md"},
        {"index": 2, "file_path": "Notes/b.md"},
    ]

    result = RagHandler._cited_sources("结论一。[2] 重复引用 [2]；无效 [9]", citations)

    assert result == [{"index": 2, "file_path": "Notes/b.md"}]


def test_cited_sources_preserves_answer_reference_order() -> None:
    citations = [
        {"index": 1, "file_path": "Notes/a.md"},
        {"index": 2, "file_path": "Notes/b.md"},
    ]

    result = RagHandler._cited_sources("先引用 [2]，再引用 [1]。", citations)

    assert [row["index"] for row in result] == [2, 1]


def test_rag_context_numbers_only_direct_evidence_and_returns_used_source(monkeypatch, tmp_path) -> None:
    config.workspace_path = str(tmp_path)
    events = []
    handler = RagHandler(
        SimpleNamespace(
            _ctx=SimpleNamespace(config=config, logger=None),
            _send_response=lambda resp: events.append(resp),
        )
    )
    captured = {}
    monkeypatch.setattr(
        "sidecar.classic_retriever.retrieve",
        lambda *_args, **_kwargs: [
            {"content": "宽泛综述", "file_path": "wiki/topic.md", "source_type": "survey"},
            {
                "content": "直接证据 A",
                "file_path": "Notes/a.md",
                "file_name": "a.md",
                "source_type": "vector",
                "score": 0.8,
            },
            {
                "content": "当前文件直接证据 B",
                "file_path": "Notes/current.md",
                "file_name": "current.md",
                "source_type": "current",
                "score": 0.7,
            },
        ],
    )

    def fake_stream(prompt, **kwargs):
        captured["prompt"] = prompt
        return "答案由当前文件支持。[2]\n【存档建议】否"

    monkeypatch.setattr("utils.llm_utils.call_llm_raw_stream", fake_stream)

    result = handler._answer_with_rag({}, "问题", "", use_vector_rag=False)

    assert result["success"] is True
    assert "宽泛综述" not in captured["prompt"]
    assert "[1] a.md" in captured["prompt"]
    assert "[2] current.md" in captured["prompt"]
    payload = events[-1]["result"]
    assert [row["file_path"] for row in payload["citations"]] == ["Notes/current.md"]


def test_limited_history_keeps_only_recent_messages() -> None:
    history = [{"role": "user", "content": f"message-{i}"} for i in range(8)]

    result = RagHandler._limited_history(history)

    assert "message-0" not in result
    assert "message-1" not in result
    assert "message-2" in result
    assert "message-7" in result


def test_user_profile_is_read_only_background(tmp_path) -> None:
    profile_dir = tmp_path / ".ai_memory"
    profile_dir.mkdir()
    profile_path = profile_dir / "user_profile.json"
    profile_path.write_text(json.dumps({"profile_md": "偏好中文回答"}, ensure_ascii=False), encoding="utf-8")

    profile = RagHandler._load_user_profile(str(tmp_path))
    context = RagHandler._personal_context(profile, "用户: 最近的问题")

    assert profile == "偏好中文回答"
    assert "仅用于理解用户背景" in context
    assert "最近的问题" in context
    assert json.loads(profile_path.read_text(encoding="utf-8"))["profile_md"] == "偏好中文回答"


def test_empty_retrieval_switches_to_no_evidence_prompt(monkeypatch, tmp_path) -> None:
    config.workspace_path = str(tmp_path)
    events = []
    handler = RagHandler(
        SimpleNamespace(
            _ctx=SimpleNamespace(config=config, logger=None),
            _send_response=lambda resp: events.append(resp),
        )
    )
    captured = {}
    monkeypatch.setattr(
        "sidecar.classic_retriever.retrieve",
        lambda *_args, **_kwargs: [{"content": "综述内容", "file_path": "wiki/topic.md", "source_type": "survey"}],
    )

    def fake_stream(prompt, **kwargs):
        captured["prompt"] = prompt
        return "知识库中没有找到与该问题直接相关的资料。\n【存档建议】否"

    monkeypatch.setattr("utils.llm_utils.call_llm_raw_stream", fake_stream)

    result = handler._answer_with_rag({}, "完全不存在的话题", "", use_vector_rag=False)

    assert result["success"] is True
    assert "检索不到" in captured["prompt"]
    assert "直接相关的资料" in captured["prompt"]
    done = events[-1]["result"]
    assert done["type"] == "rag_chat_done"
    assert done["citations"] == []
    assert done["citation_quality"]["level"] == "none"
