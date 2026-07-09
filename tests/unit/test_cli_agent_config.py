"""Persist default CLI agent selection via UI config."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import config
from sidecar.handlers.config_handler import ConfigHandler


@pytest.fixture(autouse=True)
def _restore_cli_agent_id():
    original = config.cli_agent_id
    original_typography = dict(config.typography or {})
    yield
    config.cli_agent_id = original
    config.typography = original_typography


def test_get_ui_config_exposes_cli_agent_id() -> None:
    config.cli_agent_id = "codex"
    handler = ConfigHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))
    assert handler._get_ui_config({})["cli_agent_id"] == "codex"


def test_save_ui_config_updates_cli_agent_id(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = ConfigHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))
    monkeypatch.setattr(config, "save", lambda *args, **kwargs: (True, "ok"))

    result = handler._save_ui_config({"cli_agent_id": "claude_mcp"})
    assert result["success"] is True
    assert config.cli_agent_id == "claude_mcp"
    assert handler._get_ui_config({})["cli_agent_id"] == "claude_mcp"

    cleared = handler._save_ui_config({"cli_agent_id": ""})
    assert cleared["success"] is True
    assert config.cli_agent_id == ""


def test_save_ui_config_updates_typography(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = ConfigHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))
    monkeypatch.setattr(config, "save", lambda *args, **kwargs: (True, "ok"))

    typography = {
        "h1": {"family": "serif", "style": "bold"},
        "body": {"family": "sans", "style": "normal"},
        "quote": {"family": "serif", "style": "italic"},
    }
    result = handler._save_ui_config({"typography": typography})

    assert result["success"] is True
    assert handler._get_ui_config({})["typography"] == typography
