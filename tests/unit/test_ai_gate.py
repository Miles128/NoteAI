"""AI 总开关/分项的兜底门禁测试。"""

from __future__ import annotations

import pytest

from config import config


def test_llm_call_is_blocked_when_ai_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from utils.llm_utils import call_llm_raw

    monkeypatch.setattr(config, "ai_enabled", False, raising=False)

    with pytest.raises(RuntimeError, match="AI 功能已关闭"):
        call_llm_raw("hello")


def test_rag_chat_message_reflects_master_and_feature_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    from sidecar.handlers.rag_handler import RagHandler

    monkeypatch.setattr(config, "ai_enabled", False, raising=False)
    assert "AI 功能已关闭" in (RagHandler._ai_chat_disabled_message() or "")

    monkeypatch.setattr(config, "ai_enabled", True, raising=False)
    monkeypatch.setattr(config, "ai_chat_enabled", False, raising=False)
    assert "AI 问答已关闭" in (RagHandler._ai_chat_disabled_message() or "")

    monkeypatch.setattr(config, "ai_chat_enabled", True, raising=False)
    assert RagHandler._ai_chat_disabled_message() is None


def test_config_persists_ai_switch_fields(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ai_enabled", False, raising=False)
    monkeypatch.setattr(config, "ai_writing_enabled", False, raising=False)

    target = tmp_path / "config.json"
    ok, message = config.save_to_file(str(target))
    assert ok, message

    import json

    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["ai_enabled"] is False
    assert saved["ai_writing_enabled"] is False
    assert "ai_chat_enabled" in saved
    assert "ai_compile_enabled" in saved
