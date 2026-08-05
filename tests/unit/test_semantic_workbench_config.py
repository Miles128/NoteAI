"""Semantic workbench visibility config persisted via UI config."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sidecar.handlers.config_handler import ConfigHandler

from config import config


def _handler() -> ConfigHandler:
    return ConfigHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))


@pytest.fixture
def _restore_semantic_settings():
    snapshot = {
        "semantic_workbench_enabled": config.semantic_workbench_enabled,
        "semantic_workbench_tabs": list(config.semantic_workbench_tabs),
        "semantic_workbench_intensity": config.semantic_workbench_intensity,
    }
    yield
    for key, value in snapshot.items():
        setattr(config, key, value)


def test_get_ui_config_exposes_semantic_workbench_fields(_restore_semantic_settings) -> None:
    config.semantic_workbench_enabled = False
    config.semantic_workbench_tabs = ["objects", "claims"]
    config.semantic_workbench_intensity = "light"
    ui = _handler()._get_ui_config({})
    assert ui["semantic_workbench_enabled"] is False
    assert ui["semantic_workbench_tabs"] == ["objects", "claims"]
    assert ui["semantic_workbench_intensity"] == "light"


def test_save_ui_config_validates_semantic_workbench_fields(
    monkeypatch: pytest.MonkeyPatch, _restore_semantic_settings
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
    assert config.semantic_workbench_enabled is False
    # 非法类别被剔除，合法类别保留
    assert config.semantic_workbench_tabs == ["objects", "links"]
    # 非法强度保持原值（默认 standard）
    assert config.semantic_workbench_intensity == "standard"


def test_save_ui_config_ignores_empty_tab_list_and_saves_valid_intensity(
    monkeypatch: pytest.MonkeyPatch, _restore_semantic_settings
) -> None:
    monkeypatch.setattr(config, "save", lambda *args, **kwargs: (True, "ok"))
    handler = _handler()

    handler._save_ui_config(
        {
            "semantic_workbench_enabled": True,
            "semantic_workbench_tabs": ["claims"],
            "semantic_workbench_intensity": "deep",
        }
    )
    assert config.semantic_workbench_enabled is True
    assert config.semantic_workbench_tabs == ["claims"]
    assert config.semantic_workbench_intensity == "deep"

    handler._save_ui_config({"semantic_workbench_tabs": []})
    # 空列表不覆盖已有配置
    assert config.semantic_workbench_tabs == ["claims"]
