"""ONNX 线程上限与精排器空闲卸载的单元测试。"""

from __future__ import annotations

import time

import pytest


def test_onnx_threads_default_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from sidecar.rag import embedder

    monkeypatch.delenv("NOTEAI_ONNX_THREADS", raising=False)
    monkeypatch.setattr(embedder.os, "cpu_count", lambda: 16)
    assert embedder._onnx_inference_threads() == 4

    monkeypatch.setattr(embedder.os, "cpu_count", lambda: 2)
    assert embedder._onnx_inference_threads() == 2


def test_onnx_threads_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from sidecar.rag import embedder

    monkeypatch.setenv("NOTEAI_ONNX_THREADS", "2")
    assert embedder._onnx_inference_threads() == 2

    monkeypatch.setenv("NOTEAI_ONNX_THREADS", "not-a-number")
    assert embedder._onnx_inference_threads() <= 4


def test_reranker_unloads_after_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    from sidecar.rag import reranker

    class DummyReranker:
        pass

    monkeypatch.setattr(reranker, "rerank_enabled", lambda: True)
    monkeypatch.setattr(reranker, "RERANK_IDLE_UNLOAD_SECONDS", 0.05)
    monkeypatch.setattr(reranker, "_load_onnx_reranker", lambda: DummyReranker())

    try:
        assert reranker.get_reranker() is not None
        assert reranker._RERANKER is not None

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and reranker._RERANKER is not None:
            time.sleep(0.02)
        assert reranker._RERANKER is None
    finally:
        reranker.reset_reranker()


def test_embedder_unloads_after_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    from sidecar.rag import embedder

    class DummyEmbedder:
        def embed(self, texts):
            raise AssertionError("should not embed in this test")

    monkeypatch.setattr(embedder, "_create_dense_model", lambda cb=None: DummyEmbedder())
    monkeypatch.setattr(embedder, "EMBED_IDLE_UNLOAD_SECONDS", 0.05)

    try:
        assert embedder.get_model() is not None
        assert embedder._DENSE_MODEL is not None

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and embedder._DENSE_MODEL is not None:
            time.sleep(0.02)
        assert embedder._DENSE_MODEL is None
    finally:
        embedder.reset_dense_model()
