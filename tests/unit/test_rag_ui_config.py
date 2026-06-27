"""RAG advanced settings persisted via UI config."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import config
from sidecar.handlers.config_handler import ConfigHandler


def _handler() -> ConfigHandler:
    return ConfigHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))


@pytest.fixture
def _restore_rag_settings():
    snapshot = {
        "rag_hyde_enabled": config.rag_hyde_enabled,
        "rag_hyde_threshold": config.rag_hyde_threshold,
        "rag_rerank_enabled": config.rag_rerank_enabled,
        "rag_rerank_skip_score": config.rag_rerank_skip_score,
        "rag_dense_weight": config.rag_dense_weight,
        "rag_top_k": config.rag_top_k,
        "rag_top_k_tags": config.rag_top_k_tags,
    }
    yield
    for key, value in snapshot.items():
        setattr(config, key, value)


def test_get_ui_config_exposes_rag_advanced_fields(_restore_rag_settings) -> None:
    config.rag_dense_weight = 0.6
    config.rag_hyde_enabled = False
    handler = _handler()
    ui = handler._get_ui_config({})
    assert ui["rag_dense_weight"] == 0.6
    assert ui["rag_hyde_enabled"] is False
    assert ui["rag_rerank_model"] == "BAAI/bge-reranker-v2-m3"


def test_save_ui_config_clamps_rag_advanced_fields(
    monkeypatch: pytest.MonkeyPatch, _restore_rag_settings
) -> None:
    monkeypatch.setattr(config, "save", lambda *args, **kwargs: (True, "ok"))
    handler = _handler()

    result = handler._save_ui_config(
        {
            "rag_dense_weight": 1.5,
            "rag_hyde_threshold": -0.2,
            "rag_rerank_skip_score": 2.0,
            "rag_top_k": 0,
            "rag_top_k_tags": 999,
        }
    )
    assert result["success"] is True
    assert config.rag_dense_weight == 1.0
    assert config.rag_hyde_threshold == 0.0
    assert config.rag_rerank_skip_score == 1.0
    assert config.rag_top_k == 1
    assert config.rag_top_k_tags == 50
