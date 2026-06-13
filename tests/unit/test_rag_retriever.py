"""Unit tests for RAG retriever: _reranker_enabled and _get_reranker."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest
import sidecar.rag.retriever as _mod


@pytest.fixture(autouse=True)
def _reset_reranker_globals():
    original_reranker = _mod._RERANKER
    original_disabled = _mod._RERANKER_DISABLED
    _mod._RERANKER = None
    _mod._RERANKER_DISABLED = False
    yield
    _mod._RERANKER = original_reranker
    _mod._RERANKER_DISABLED = original_disabled


@pytest.fixture()
def _mock_embedder_module(monkeypatch):
    fake_embedder = ModuleType("sidecar.rag.embedder")
    fake_embedder._ensure_hf_env = MagicMock()
    monkeypatch.setitem(sys.modules, "sidecar.rag.embedder", fake_embedder)
    return fake_embedder


class TestRerankerEnabled:
    def test_default_returns_true(self, monkeypatch):
        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        monkeypatch.delenv("NOTEAI_ENABLE_RERANKER", raising=False)
        assert _mod._reranker_enabled() is True

    def test_disable_env_1(self, monkeypatch):
        monkeypatch.setenv("NOTEAI_DISABLE_RERANKER", "1")
        assert _mod._reranker_enabled() is False

    def test_disable_env_true(self, monkeypatch):
        monkeypatch.setenv("NOTEAI_DISABLE_RERANKER", "true")
        assert _mod._reranker_enabled() is False

    def test_disable_env_yes(self, monkeypatch):
        monkeypatch.setenv("NOTEAI_DISABLE_RERANKER", "yes")
        assert _mod._reranker_enabled() is False

    def test_disable_env_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("NOTEAI_DISABLE_RERANKER", "True")
        assert _mod._reranker_enabled() is False

    def test_disable_env_other_value(self, monkeypatch):
        monkeypatch.setenv("NOTEAI_DISABLE_RERANKER", "0")
        assert _mod._reranker_enabled() is True

    def test_enable_env_1(self, monkeypatch):
        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        monkeypatch.setenv("NOTEAI_ENABLE_RERANKER", "1")
        assert _mod._reranker_enabled() is True

    def test_enable_env_true(self, monkeypatch):
        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        monkeypatch.setenv("NOTEAI_ENABLE_RERANKER", "true")
        assert _mod._reranker_enabled() is True

    def test_disable_takes_precedence_over_enable(self, monkeypatch):
        monkeypatch.setenv("NOTEAI_DISABLE_RERANKER", "1")
        monkeypatch.setenv("NOTEAI_ENABLE_RERANKER", "1")
        assert _mod._reranker_enabled() is False


class TestGetReranker:
    @pytest.fixture(autouse=True)
    def _reranker_enabled_unless_test_sets_disable(self, monkeypatch):
        """Job-level NOTEAI_DISABLE_RERANKER=1 in CI must not leak into enable tests."""
        monkeypatch.setenv("NOTEAI_DISABLE_RERANKER", "0")
        monkeypatch.delenv("NOTEAI_ENABLE_RERANKER", raising=False)

    def test_returns_none_when_disabled(self, monkeypatch):
        monkeypatch.setenv("NOTEAI_DISABLE_RERANKER", "1")
        assert _mod._get_reranker() is None

    def test_returns_none_when_disabled_flag_set(self, monkeypatch):
        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        _mod._RERANKER_DISABLED = True
        assert _mod._get_reranker() is None

    def test_returns_cached_reranker(self):
        sentinel = object()
        _mod._RERANKER = sentinel
        assert _mod._get_reranker() is sentinel

    def test_sets_disabled_flag_on_import_error(self, monkeypatch, _mock_embedder_module):
        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        monkeypatch.setitem(sys.modules, "FlagEmbedding", None)

        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                raise ImportError("no FlagEmbedding")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _fake_import)

        result = _mod._get_reranker()
        assert result is None
        assert _mod._RERANKER_DISABLED is True

    def test_sets_disabled_flag_on_generic_exception(self, monkeypatch, _mock_embedder_module):
        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        _mock_embedder_module._ensure_hf_env = MagicMock(side_effect=RuntimeError("boom"))

        result = _mod._get_reranker()
        assert result is None
        assert _mod._RERANKER_DISABLED is True

    def test_returns_none_after_previous_failure(self, monkeypatch):
        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        _mod._RERANKER_DISABLED = True
        assert _mod._get_reranker() is None
