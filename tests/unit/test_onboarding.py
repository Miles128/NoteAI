"""Tests for first-run onboarding RPCs.

Covers:
- workspace_handler.get_onboarding_status / mark_onboarding_done
- config_handler.test_api_config (connectivity check only, never persists)
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sidecar.handlers.config_handler import ConfigHandler
from sidecar.handlers.workspace_handler import WorkspaceHandler
from sidecar.rag.model_preload import ModelWarmupManager

from config import config


def _config_handler() -> ConfigHandler:
    return ConfigHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))


def _workspace_handler() -> WorkspaceHandler:
    server = SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None))
    return WorkspaceHandler(server)


# ---------------------------------------------------------------------------
# get_onboarding_status
# ---------------------------------------------------------------------------


def test_get_onboarding_status_without_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sidecar.handlers.workspace_handler.workspace_manager.load_workspace",
        lambda: (None, {}),
    )
    monkeypatch.setattr(ModelWarmupManager, "is_ready", classmethod(lambda cls: False))
    prev_key = config.api_key
    config.api_key = ""
    try:
        status = _workspace_handler()._get_onboarding_status({})
    finally:
        config.api_key = prev_key

    assert status["workspace_set"] is False
    assert status["workspace_path"] == ""
    assert status["api_key_configured"] is False
    assert status["models_ready"] is False
    assert status["onboarding_done"] is False


def test_get_onboarding_status_reflects_ready_states(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setattr(
        "sidecar.handlers.workspace_handler.workspace_manager.load_workspace",
        lambda: (str(workspace), {"workspace_path": str(workspace), "onboarding_done": True}),
    )
    monkeypatch.setattr(ModelWarmupManager, "is_ready", classmethod(lambda cls: True))
    prev_key = config.api_key
    config.api_key = "sk-test-key"
    try:
        status = _workspace_handler()._get_onboarding_status({})
    finally:
        config.api_key = prev_key

    assert status["workspace_set"] is True
    assert status["workspace_path"] == str(workspace)
    assert status["api_key_configured"] is True
    assert status["models_ready"] is True
    assert status["onboarding_done"] is True


def test_get_onboarding_status_missing_workspace_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sidecar.handlers.workspace_handler.workspace_manager.load_workspace",
        lambda: ("/nonexistent/path/for/onboarding/test", {}),
    )
    monkeypatch.setattr(ModelWarmupManager, "is_ready", classmethod(lambda cls: False))
    status = _workspace_handler()._get_onboarding_status({})
    assert status["workspace_set"] is False


# ---------------------------------------------------------------------------
# mark_onboarding_done
# ---------------------------------------------------------------------------


def test_mark_onboarding_done_persists_additional_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    saved_calls: list[dict] = []

    monkeypatch.setattr(
        "sidecar.handlers.workspace_handler.workspace_manager.load_workspace",
        lambda: (str(workspace), {"workspace_path": str(workspace), "custom_flag": 1}),
    )

    def fake_save(path, additional_data=None):
        saved_calls.append({"path": path, "additional_data": additional_data})
        return True, "ok"

    monkeypatch.setattr("sidecar.handlers.workspace_handler.workspace_manager.save_workspace", fake_save)

    result = _workspace_handler()._mark_onboarding_done({})
    assert result == {"success": True, "persisted": True}
    assert len(saved_calls) == 1
    assert saved_calls[0]["path"] == str(workspace)
    extra = saved_calls[0]["additional_data"]
    assert extra["onboarding_done"] is True
    # 既有 additional_data 字段不丢失
    assert extra["custom_flag"] == 1
    # save_workspace 自身管理的字段不回传，避免覆盖新时间戳
    assert "workspace_path" not in extra
    assert "last_opened_at" not in extra
    assert "version" not in extra


def test_mark_onboarding_done_without_workspace_skips_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sidecar.handlers.workspace_handler.workspace_manager.load_workspace",
        lambda: (None, {}),
    )
    result = _workspace_handler()._mark_onboarding_done({})
    assert result == {"success": True, "persisted": False}


def test_mark_onboarding_done_save_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setattr(
        "sidecar.handlers.workspace_handler.workspace_manager.load_workspace",
        lambda: (str(workspace), {}),
    )
    monkeypatch.setattr(
        "sidecar.handlers.workspace_handler.workspace_manager.save_workspace",
        lambda path, additional_data=None: (False, "磁盘写入失败"),
    )
    result = _workspace_handler()._mark_onboarding_done({})
    assert result["success"] is False
    assert "磁盘写入失败" in result["message"]


# ---------------------------------------------------------------------------
# test_api_config（config_handler，仅测试不落盘）
# ---------------------------------------------------------------------------


def test_test_api_config_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_test(api_key, api_base, model_name, disable_thinking=None):
        captured.update({"api_key": api_key, "api_base": api_base, "model_name": model_name})
        return True, "API 连接成功"

    monkeypatch.setattr("sidecar.handlers.config_handler.test_api_connection", fake_test)
    result = _config_handler()._test_api_config(
        {"api_key": "sk-1234567890", "api_base": "https://api.deepseek.com", "model_name": "deepseek-chat"}
    )
    assert result["success"] is True
    assert result["connected"] is True
    assert captured["api_key"] == "sk-1234567890"


def test_test_api_config_failure_returns_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sidecar.handlers.config_handler.test_api_connection",
        lambda k, b, m, disable_thinking=None: (False, "认证失败：401"),
    )
    result = _config_handler()._test_api_config({"api_key": "sk-1234567890"})
    assert result["success"] is False
    assert result["connected"] is False
    assert "401" in result["message"]


def test_test_api_config_rejects_empty_and_masked_key(monkeypatch: pytest.MonkeyPatch) -> None:
    called = []

    def fake_test(*args, **kwargs):
        called.append(args)
        return True, "ok"

    monkeypatch.setattr("sidecar.handlers.config_handler.test_api_connection", fake_test)
    handler = _config_handler()

    empty = handler._test_api_config({"api_key": ""})
    assert empty["success"] is False
    masked = handler._test_api_config({"api_key": "sk-1■■■■abcd"})
    assert masked["success"] is False
    assert called == []  # 无效入参不触发真实连接测试


def test_test_api_config_does_not_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sidecar.handlers.config_handler.test_api_connection",
        lambda k, b, m, disable_thinking=None: (True, "ok"),
    )
    prev_key, prev_base, prev_model = config.api_key, config.api_base, config.model_name
    try:
        _config_handler()._test_api_config(
            {"api_key": "sk-newkey-12345", "api_base": "http://localhost:11434/v1", "model_name": "qwen2.5:7b"}
        )
        assert config.api_key == prev_key
        assert config.api_base == prev_base
        assert config.model_name == prev_model
    finally:
        config.api_key, config.api_base, config.model_name = prev_key, prev_base, prev_model
