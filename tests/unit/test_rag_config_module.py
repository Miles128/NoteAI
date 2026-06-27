"""Runtime RAG config helpers."""

from __future__ import annotations

import pytest

from config import config
from sidecar.rag import rag_config


@pytest.fixture
def _restore_rag_settings():
    snapshot = {
        "rag_hyde_enabled": config.rag_hyde_enabled,
        "rag_hyde_threshold": config.rag_hyde_threshold,
        "rag_rerank_enabled": config.rag_rerank_enabled,
        "rag_dense_weight": config.rag_dense_weight,
        "rag_top_k": config.rag_top_k,
        "rag_top_k_tags": config.rag_top_k_tags,
    }
    yield
    for key, value in snapshot.items():
        setattr(config, key, value)


def test_hybrid_weights_from_config(_restore_rag_settings) -> None:
    config.rag_dense_weight = 0.8
    dense, sparse = rag_config.hybrid_weights()
    assert dense == pytest.approx(0.8)
    assert sparse == pytest.approx(0.2)


def test_top_k_respects_filters(_restore_rag_settings) -> None:
    config.rag_top_k = 4
    config.rag_top_k_tags = 9
    assert rag_config.top_k(has_filters=False) == 4
    assert rag_config.top_k(has_filters=True) == 9


def test_hyde_can_be_disabled(_restore_rag_settings) -> None:
    config.rag_hyde_enabled = False
    assert rag_config.hyde_enabled() is False
