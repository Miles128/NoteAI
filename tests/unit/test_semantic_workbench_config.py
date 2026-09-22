"""Semantic workbench display prefs live in frontend localStorage.

Backend no longer persists semantic_workbench_enabled/tabs/intensity
(_get_ui_config omits them, _save_ui_config ignores them).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sidecar.handlers.config_handler import ConfigHandler

from config import config


def _handler() -> ConfigHandler:
    return ConfigHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))


def test_get_ui_config_omits_semantic_workbench_fields() -> None:
    ui = _handler()._get_ui_config({})
    assert "semantic_workbench_enabled" not in ui
    assert "semantic_workbench_tabs" not in ui
    assert "semantic_workbench_intensity" not in ui


def test_save_ui_config_ignores_semantic_workbench_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "save", lambda *args, **kwargs: (True, "ok"))
    handler = _handler()

    result = handler._save_ui_config(
        {
            "semantic_workbench_enabled": False,
            "semantic_workbench_tabs": ["objects", "links", "bogus"],
            "semantic_workbench_intensity": "ultra",
        }
    )
    assert result["success"] is True
    assert not hasattr(config, "semantic_workbench_enabled")
    assert not hasattr(config, "semantic_workbench_tabs")
    assert not hasattr(config, "semantic_workbench_intensity")
