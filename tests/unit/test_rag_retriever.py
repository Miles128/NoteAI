"""Unit tests for RAG retriever: _reranker_enabled and _get_reranker."""

import pytest
import sidecar.rag.retriever as _mod


@pytest.fixture(autouse=True)
def _reset_reranker_globals():
    import sidecar.rag.reranker as rk

    original_reranker = rk._RERANKER
    original_disabled_until = rk._RERANKER_DISABLED_UNTIL
    rk._RERANKER = None
    rk._RERANKER_DISABLED_UNTIL = 0.0
    yield
    rk._RERANKER = original_reranker
    rk._RERANKER_DISABLED_UNTIL = original_disabled_until


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


def test_scan_files_indexes_only_non_readme_notes(tmp_path):
    notes = tmp_path / "Notes"
    (notes / "AI").mkdir(parents=True)
    (notes / "AI" / "note.md").write_text("# note", encoding="utf-8")
    (notes / "AI" / "README.md").write_text("# guide", encoding="utf-8")
    (tmp_path / "README.md").write_text("# project", encoding="utf-8")
    (tmp_path / ".reasonix").mkdir()
    (tmp_path / ".reasonix" / "tool.md").write_text("# tool", encoding="utf-8")

    files = _mod._scan_files(tmp_path)

    assert set(files) == {"Notes/AI/note.md"}


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
        import time

        import sidecar.rag.reranker as rk

        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        rk._RERANKER_DISABLED_UNTIL = time.time() + 60
        assert _mod._get_reranker() is None

    def test_returns_cached_reranker(self):
        import sidecar.rag.reranker as rk

        sentinel = object()
        rk._RERANKER = sentinel
        assert _mod._get_reranker() is sentinel

    def test_sets_disabled_flag_on_load_error(self, monkeypatch):
        import time

        import sidecar.rag.reranker as rk

        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        monkeypatch.setattr(rk, "_load_onnx_reranker", lambda: (_ for _ in ()).throw(ImportError("no onnx")))

        result = _mod._get_reranker()
        assert result is None
        assert time.time() < rk._RERANKER_DISABLED_UNTIL

    def test_returns_none_after_previous_failure(self, monkeypatch):
        import time

        import sidecar.rag.reranker as rk

        monkeypatch.delenv("NOTEAI_DISABLE_RERANKER", raising=False)
        rk._RERANKER_DISABLED_UNTIL = time.time() + 60
        assert _mod._get_reranker() is None


class TestDynamicTopK:
    def _hit(self, idx: int, score: float, topic: str = "AI > RAG") -> dict:
        return {
            "id": f"h{idx}",
            "content": f"chunk {idx}",
            "file_path": f"Notes/{idx}.md",
            "topic": topic,
            "score": score,
        }

    def test_easy_high_confidence_query_keeps_citations_tight(self):
        hits = [self._hit(1, 0.9), self._hit(2, 0.62), self._hit(3, 0.5)]
        assert _mod.select_dynamic_top_k("什么是 RAG", hits) == 2

    def test_broad_diverse_query_expands_citations(self):
        hits = [self._hit(i, 0.75 - i * 0.02, topic=f"AI > T{i % 5}") for i in range(1, 11)]
        assert _mod.select_dynamic_top_k("请总结并比较这些资料有哪些方案、优缺点和路线", hits) == 8

    def test_weak_evidence_does_not_pad_citations(self):
        hits = [self._hit(1, 0.18), self._hit(2, 0.15), self._hit(3, 0.12)]
        assert _mod.select_dynamic_top_k("NoteAI", hits) == 2

    def test_empty_chunks_are_ignored(self):
        hits = [self._hit(1, 0.9), {**self._hit(2, 0.8), "content": ""}]
        assert _mod.select_dynamic_top_k("什么是 RAG", hits) == 1

    def test_limit_unique_sources_keeps_multiple_chunks_from_selected_files(self):
        hits = [
            {**self._hit(1, 0.9), "id": "a1", "file_path": "Notes/a.md"},
            {**self._hit(2, 0.8), "id": "a2", "file_path": "Notes/a.md"},
            {**self._hit(3, 0.7), "id": "b1", "file_path": "Notes/b.md"},
            {**self._hit(4, 0.6), "id": "c1", "file_path": "Notes/c.md"},
        ]
        limited = _mod.limit_unique_sources(hits, 2)
        assert [h["id"] for h in limited] == ["a1", "a2", "b1"]
