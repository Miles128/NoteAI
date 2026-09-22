"""ONNX reranker: load via fastembed TextCrossEncoder, no FlagEmbedding/torch."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
import sidecar.rag.reranker as rk


@pytest.fixture(autouse=True)
def _reset_reranker_globals():
    original = rk._RERANKER
    original_until = rk._RERANKER_DISABLED_UNTIL
    original_registered = rk._CUSTOM_REGISTERED
    rk._RERANKER = None
    rk._RERANKER_DISABLED_UNTIL = 0.0
    rk._CUSTOM_REGISTERED = False
    yield
    rk._RERANKER = original
    rk._RERANKER_DISABLED_UNTIL = original_until
    rk._CUSTOM_REGISTERED = original_registered


def test_score_documents_uses_rerank_not_flagembedding():
    calls = []

    class FakeEncoder:
        def rerank(self, query, documents, batch_size=64):
            calls.append((query, list(documents), batch_size))
            return [2.0, 0.5]

    scores = rk.score_documents(FakeEncoder(), "q", ["a", "b"])
    assert scores == [2.0, 0.5]
    assert calls == [("q", ["a", "b"], 64)]


def test_get_reranker_returns_cached_instance(monkeypatch):
    from config import config

    monkeypatch.setattr(config, "rag_rerank_enabled", True)
    sentinel = object()
    rk._RERANKER = sentinel
    assert rk.get_reranker() is sentinel


def test_get_reranker_none_when_disabled(monkeypatch):
    from config import config

    monkeypatch.setattr(config, "rag_rerank_enabled", False)
    assert rk.get_reranker() is None


def test_get_reranker_cools_down_on_load_error(monkeypatch):
    from config import config

    monkeypatch.setattr(config, "rag_rerank_enabled", True)
    monkeypatch.setattr(rk, "_load_onnx_reranker", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert rk.get_reranker() is None
    assert time.time() < rk._RERANKER_DISABLED_UNTIL


def test_reset_reranker_clears_cache():
    rk._RERANKER = object()
    rk._RERANKER_DISABLED_UNTIL = 99.0
    rk.reset_reranker()
    assert rk._RERANKER is None
    assert rk._RERANKER_DISABLED_UNTIL == 0.0


def test_load_uses_fastembed_cross_encoder(monkeypatch):
    captured = {}

    class FakeTextCrossEncoder:
        def __init__(self, model_name, cache_dir=None, threads=None):
            captured["model_name"] = model_name
            captured["cache_dir"] = cache_dir
            captured["threads"] = threads

    monkeypatch.setattr(rk, "TextCrossEncoder", FakeTextCrossEncoder)
    monkeypatch.setattr(rk, "_cache_dir", lambda: "/tmp/fe")
    monkeypatch.setattr(rk, "_onnx_threads", lambda: 4)
    model = rk._load_onnx_reranker()
    assert isinstance(model, FakeTextCrossEncoder)
    assert captured["model_name"] == "Xenova/bge-reranker-base"
    assert captured["cache_dir"] == "/tmp/fe"


def test_registers_quantized_onnx_not_fp32():
    added = []

    class FakeEncoder:
        @classmethod
        def list_supported_models(cls):
            return []

        @classmethod
        def add_custom_model(cls, **kwargs):
            added.append(kwargs)

    rk._ensure_quantized_model(FakeEncoder)
    assert added[0]["model_file"] == "onnx/model_quantized.onnx"
    assert added[0]["sources"].hf == "Xenova/bge-reranker-base"
    assert added[0]["size_in_gb"] == 0.28


def test_retriever_rerank_uses_onnx_scores(monkeypatch):
    import sidecar.rag.retriever as retriever

    fake = SimpleNamespace(rerank=lambda query, documents, batch_size=64: [0.1, 0.9])
    monkeypatch.setattr(retriever, "_get_reranker", lambda: fake)
    monkeypatch.setattr(retriever, "rerank_skip_score", lambda: 0.99)
    rows = [
        {"id": "a", "content": "first", "score": 0.2},
        {"id": "b", "content": "second", "score": 0.3},
    ]
    ranked = retriever._rerank("query", rows, top_k=2)
    assert [r["id"] for r in ranked] == ["b", "a"]
    assert ranked[0]["rerank_score"] == 0.9
