from pathlib import Path
from unittest.mock import patch

import pytest
from sidecar.ingest_pipeline import (
    cancel_generation,
    clear_cancel,
    load_ingest_state,
    request_cancel,
    run_ingest,
    save_ingest_state,
)

from config import config
from tests.workspace_rules_helpers import write_workspace_rules


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes").mkdir(parents=True)
    (d / "wiki").mkdir()
    config.workspace_path = str(d)
    return d


def test_run_ingest_completes_when_rules_configured(workspace: Path) -> None:
    write_workspace_rules(workspace)
    events: list[dict] = []
    stages: list[str] = []

    def on_progress(stage: str, progress: float, message: str, extra: dict | None = None) -> None:
        stages.append(stage)

    def on_event(resp: dict) -> None:
        events.append(resp.get("result", {}))

    with (
        patch("sidecar.ingest_pipeline.sync_wiki_with_files"),
        patch("utils.note_compiler.compile_notes_batch", return_value=(0, [])),
        patch("sidecar.ingest_pipeline._index_markdown_files", return_value=(0, [])),
    ):
        result = run_ingest(mode="full", send_progress=on_progress, send_event=on_event)

    assert result["success"] is True
    assert "rules" in stages
    assert "semantic" in stages
    assert "sync" in stages
    assert any(e.get("type") == "ingest_complete" for e in events)
    assert load_ingest_state()["status"] == "complete"


def test_semantic_stage_failure_does_not_block_ingest(workspace: Path) -> None:
    write_workspace_rules(workspace)
    note = workspace / "Notes" / "RAG" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\ntopic: RAG\n---\n\n正文。", encoding="utf-8")

    semantic_result = {
        "documents": 1,
        "blocks": 1,
        "extracted_blocks": 0,
        "claims": 0,
        "failed_blocks": 1,
        "pending_documents": 0,
        "topics": ["RAG"],
        "failures": [{"file": "Notes/RAG/note.md", "error": "bad json"}],
    }
    with (
        patch("sidecar.ingest_pipeline._scan_convert_pending", return_value=[]),
        patch("utils.note_compiler.scan_compile_pending", return_value=[]),
        patch("sidecar.ingest_pipeline._scan_classify_pending", return_value=[]),
        patch("sidecar.topic_placement.auto_move_misplaced_notes", return_value={"moved": []}),
        patch("sidecar.semantic.compiler.compile_semantic_batch", return_value=semantic_result),
        patch("sidecar.semantic.topic_state.materialize_topic_state"),
        patch("sidecar.ingest_pipeline._index_markdown_files", return_value=(1, ["Notes/RAG/note.md"])),
        patch("sidecar.ingest_pipeline.sync_wiki_with_files"),
        patch("sidecar.kb_lint.run_kb_lint", return_value={"issues": [], "summary": {"total": 0}}),
        patch("sidecar.kb_lint.log_lint_report"),
    ):
        result = run_ingest(mode="full")

    assert result["success"] is True
    assert result["stats"]["semantic_failed_blocks"] == 1
    assert result["stats"]["semantic_documents"] == 1


def test_run_ingest_respects_cancel(workspace: Path) -> None:
    write_workspace_rules(workspace)
    request_cancel()

    with patch("sidecar.ingest_pipeline.clear_cancel"), patch("sidecar.ingest_pipeline.sync_wiki_with_files"):
        result = run_ingest(mode="full")

    assert result.get("cancelled") is True
    assert load_ingest_state()["status"] == "cancelled"
    clear_cancel()


def test_cancel_after_scheduling_is_not_cleared_at_worker_start(workspace: Path) -> None:
    write_workspace_rules(workspace)
    token = cancel_generation()
    request_cancel()

    with patch("sidecar.ingest_pipeline.sync_wiki_with_files"):
        result = run_ingest(mode="full", cancel_after_generation=token)

    assert result.get("cancelled") is True
    clear_cancel()


def test_incremental_up_to_date_uses_full_progress_callback_contract(workspace: Path) -> None:
    save_state = {
        "status": "complete",
        "last_complete_at": 1.0,
    }
    save_ingest_state(save_state)
    progress_calls: list[tuple[str, float, str, dict | None]] = []

    def on_progress(stage: str, progress: float, message: str, extra: dict | None) -> None:
        progress_calls.append((stage, progress, message, extra))

    with (
        patch("sidecar.ingest_pipeline._workspace_has_pending_ingest", return_value=False),
        patch("sidecar.ingest_pipeline._workspace_files_changed", return_value=(False, {})),
        patch("sidecar.ingest_pipeline._save_fingerprint"),
    ):
        result = run_ingest(mode="incremental", send_progress=on_progress)

    assert result["up_to_date"] is True
    assert progress_calls == [("sync", 1.0, "工作区已是最新，跳过自检", None)]


def test_scan_index_pending_finds_changed_notes(workspace: Path) -> None:
    from sidecar.ingest_pipeline import _scan_index_pending

    md = workspace / "Notes" / "changed.md"
    md.write_text("# hello", encoding="utf-8")
    pending = _scan_index_pending(str(workspace))
    assert md in pending


def test_empty_note_deletes_stale_chunks_before_marking_indexed(workspace: Path) -> None:
    from sidecar.ingest_pipeline import _index_markdown_files

    md = workspace / "Notes" / "empty.md"
    md.write_text("", encoding="utf-8")
    with (
        patch("sidecar.rag.chunker.chunk_file", return_value=[]),
        patch("sidecar.rag.index.replace_file_chunks", return_value=0) as replace_chunks,
        patch("sidecar.rag.index_state.mark_many_indexed") as mark_many,
    ):
        indexed, paths = _index_markdown_files(str(workspace), [md], None)

    assert indexed == 1
    assert paths == ["Notes/empty.md"]
    payload = replace_chunks.call_args.args[1]["Notes/empty.md"]
    assert payload["chunks"] == []
    mark_many.assert_called_once()


def test_failed_batch_write_does_not_commit_index_state(workspace: Path) -> None:
    from sidecar.ingest_pipeline import _index_markdown_files

    md = workspace / "Notes" / "note.md"
    md.write_text("# note", encoding="utf-8")

    with (
        patch("sidecar.rag.chunker.chunk_file", return_value=[{"content": "note"}]),
        patch("sidecar.rag.embedder.encode_documents", return_value=[{"dense": [0.1]}]),
        patch("sidecar.rag.index.replace_file_chunks", side_effect=RuntimeError("index write failed")),
        patch("sidecar.rag.index_state.mark_many_indexed") as mark_many,
        pytest.raises(RuntimeError, match="index write failed"),
    ):
        _index_markdown_files(str(workspace), [md], None)

    mark_many.assert_not_called()


def test_integrity_mismatch_repairs_all_notes(workspace: Path) -> None:
    from sidecar.ingest_pipeline import _index_markdown_files

    first = workspace / "Notes" / "a.md"
    second = workspace / "Notes" / "b.md"
    first.write_text("# a", encoding="utf-8")
    second.write_text("# b", encoding="utf-8")

    with (
        patch(
            "sidecar.rag.index.load_manifest",
            return_value={"files": {"Notes/a.md": {"chunks": ["old-a"]}, "Notes/b.md": {"chunks": ["old-b"]}}},
        ),
        patch("sidecar.rag.index.count_indexed_chunks", return_value=0),
        patch(
            "sidecar.rag.chunker.chunk_file",
            side_effect=lambda rel, _text: [{"id": rel, "content": rel}],
        ),
        patch("sidecar.rag.embedder.encode_documents", return_value=[{"dense_vec": [0.1]}]),
        patch("sidecar.rag.index.replace_file_chunks", return_value=2) as replace_chunks,
        patch("sidecar.rag.index_state.mark_many_indexed"),
    ):
        indexed, paths = _index_markdown_files(str(workspace), [first], None)

    assert indexed == 2
    assert set(paths) == {"Notes/a.md", "Notes/b.md"}
    assert set(replace_chunks.call_args.args[1]) == {"Notes/a.md", "Notes/b.md"}


def test_convert_failure_does_not_commit_convert_stage(workspace: Path) -> None:
    write_workspace_rules(workspace)

    class FailingConverter:
        def convert_batch(self, *_args, **_kwargs) -> list[dict]:
            return [{"success": False, "error": "broken document"}]

    with (
        patch("sidecar.ingest_pipeline._scan_convert_pending", return_value=["broken.pdf"]),
        patch("sidecar.ingest_pipeline.FileConverterManager", return_value=FailingConverter()),
    ):
        result = run_ingest(mode="full")

    state = load_ingest_state()
    assert result["success"] is False
    assert state["status"] == "failed"
    assert state["completed_stages"] == ["rules"]


def test_classify_failure_does_not_commit_classify_stage(workspace: Path) -> None:
    write_workspace_rules(workspace)
    note = workspace / "Notes" / "broken.md"
    note.write_text("# broken", encoding="utf-8")

    with (
        patch("sidecar.ingest_pipeline._scan_convert_pending", return_value=[]),
        patch("utils.note_compiler.scan_compile_pending", return_value=[]),
        patch("sidecar.ingest_pipeline._scan_classify_pending", return_value=[note]),
        patch(
            "sidecar.ingest_pipeline.auto_assign_topic_for_file",
            return_value={"status": "error", "message": "move failed"},
        ),
    ):
        result = run_ingest(mode="full")

    state = load_ingest_state()
    assert result["success"] is False
    assert state["status"] == "failed"
    assert state["completed_stages"] == ["rules", "convert", "compile"]


def test_deleted_note_is_purged_from_chunks_before_state(workspace: Path) -> None:
    from sidecar.ingest_pipeline import _purge_deleted_index_files

    calls: list[tuple[str, object]] = []
    with (
        patch("sidecar.rag.index_state.load_state", return_value={"Notes/deleted.md": 123.0}),
        patch(
            "sidecar.rag.index.delete_by_file",
            side_effect=lambda ws, rel: calls.append(("delete", (ws, rel))),
        ),
        patch(
            "sidecar.rag.index_state.remove_indexed",
            side_effect=lambda paths, ws: calls.append(("state", (paths, ws))),
        ),
    ):
        purged = _purge_deleted_index_files(str(workspace))

    assert purged == ["Notes/deleted.md"]
    assert calls == [
        ("delete", (str(workspace), "Notes/deleted.md")),
        ("state", (["Notes/deleted.md"], str(workspace))),
    ]


def test_resume_restores_crossref_paths_and_affected_topics(workspace: Path) -> None:
    write_workspace_rules(workspace)
    save_ingest_state(
        {
            "status": "failed",
            "mode": "full",
            "completed_stages": ["rules", "convert", "compile", "classify", "index"],
            "pending_crossref_paths": ["Notes/a.md", "Notes/b.md"],
            "affected_topics": ["技术 > Python"],
        }
    )
    crossref_calls: list[str] = []

    with (
        patch(
            "utils.link_indexer.discover_cross_refs_for_file",
            side_effect=lambda rel, **_kwargs: crossref_calls.append(rel) or {"added": 0},
        ),
        patch("sidecar.ingest_pipeline.sync_wiki_with_files"),
        patch("sidecar.kb_lint.run_kb_lint", return_value={"summary": {"total": 0}}),
        patch("sidecar.kb_lint.log_lint_report"),
    ):
        result = run_ingest(mode="full", resume=True)

    assert result["success"] is True
    assert crossref_calls == ["Notes/a.md", "Notes/b.md"]
    assert result["stats"]["cascade_topics"] == ["技术 > Python"]


def test_crossref_failure_keeps_stage_retryable(workspace: Path) -> None:
    write_workspace_rules(workspace)
    save_ingest_state(
        {
            "status": "failed",
            "mode": "full",
            "completed_stages": ["rules", "convert", "compile", "classify", "index"],
            "pending_crossref_paths": ["Notes/a.md", "Notes/b.md"],
        }
    )

    with patch("utils.link_indexer.discover_cross_refs_for_file", side_effect=RuntimeError("link failed")):
        result = run_ingest(mode="full", resume=True)

    state = load_ingest_state()
    assert result["success"] is False
    assert state["status"] == "failed"
    assert "crossref" not in state["completed_stages"]
    assert state["pending_crossref_paths"] == ["Notes/a.md", "Notes/b.md"]


def test_load_ingest_state_rejects_non_object_json(workspace: Path) -> None:
    state_path = workspace / ".noteai" / "ingest_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("[]", encoding="utf-8")

    assert load_ingest_state() == {"status": "idle"}
