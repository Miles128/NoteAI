from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from sidecar import storage_usage
from sidecar.handlers.reliability_handler import ReliabilityHandler
from sidecar.rag.reranker import reset_reranker


@pytest.fixture
def app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "appdata"
    root.mkdir()
    monkeypatch.setattr(storage_usage, "SYSTEM_APP_DATA_DIR", root)
    return root


def _write_bytes(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_dir_size_bytes_empty(tmp_path: Path) -> None:
    assert storage_usage.dir_size_bytes(tmp_path / "missing") == 0
    assert storage_usage.dir_size_bytes(tmp_path) == 0


def test_dir_size_bytes_dedupes_hardlinks(tmp_path: Path) -> None:
    src = tmp_path / "blobs" / "a.bin"
    link = tmp_path / "snapshots" / "a.bin"
    _write_bytes(src, 50)
    link.parent.mkdir(parents=True)
    link.hardlink_to(src)
    assert storage_usage.dir_size_bytes(tmp_path) == 50


def test_get_storage_usage_purges_stale_fastembed(app_data: Path, tmp_path: Path) -> None:
    live = app_data / "fastembed_cache" / "models--Qdrant--bge-small-zh-v1.5" / "model.onnx"
    stale = app_data / "fastembed_cache" / "fast-bge-small-zh-v1.5" / "model_optimized.onnx"
    hf = app_data / "hf_hub" / "models--BAAI--bge-reranker-base" / "pytorch_model.bin"
    _write_bytes(live, 40)
    _write_bytes(stale, 80)
    _write_bytes(hf, 20)

    ws = tmp_path / "vault"
    index = ws / ".noteai" / "rag_index" / "chunk.bin"
    leftover = ws / "rag_index" / "old.bin"
    _write_bytes(index, 10)
    _write_bytes(leftover, 5)

    usage = storage_usage.get_storage_usage(str(ws))
    assert usage["success"] is True
    assert usage["purged_stale_bytes"] == 80
    assert not stale.parent.exists()
    assert live.exists()

    by_id = {item["id"]: item for item in usage["items"]}
    assert by_id["hf_hub"]["bytes"] == 20
    assert by_id["fastembed"]["bytes"] == 40
    assert by_id["fastembed"]["stale_bytes"] == 0
    assert by_id["index"]["bytes"] == 15
    assert usage["total_bytes"] == 75


def test_clear_storage_models_and_index(app_data: Path, tmp_path: Path) -> None:
    _write_bytes(app_data / "hf_hub" / "a.bin", 8)
    _write_bytes(app_data / "fastembed_cache" / "models--Qdrant--x" / "b.bin", 6)
    ws = tmp_path / "vault"
    note = ws / "Notes" / "keep.md"
    _write_bytes(note, 12)
    _write_bytes(ws / ".noteai" / "rag_index" / "z.bin", 4)

    result = storage_usage.clear_storage(["hf_hub", "fastembed", "index"], str(ws))
    assert result["success"] is True
    assert set(result["cleared"]) == {"hf_hub", "fastembed", "index"}
    assert result["freed_bytes"] == 18
    assert note.read_bytes() == b"x" * 12
    assert (app_data / "hf_hub").is_dir()
    assert not (app_data / "hf_hub" / "a.bin").exists()
    assert not (ws / ".noteai" / "rag_index").exists()


def test_clear_storage_rejects_unknown_and_missing_workspace(app_data: Path) -> None:
    bad = storage_usage.clear_storage(["notes"], None)
    assert bad["success"] is False
    missing_ws = storage_usage.clear_storage(["index"], None)
    assert missing_ws["success"] is False
    empty_ws = storage_usage.clear_storage(["index"], "")
    assert empty_ws["success"] is False
    root_ws = storage_usage.clear_storage(["index"], "/")
    assert root_ws["success"] is False


def test_wipe_refuses_path_outside_allowed_roots(tmp_path: Path) -> None:
    outsider = tmp_path / "outside.bin"
    _write_bytes(outsider, 3)
    freed = storage_usage._wipe_dir(outsider, [tmp_path / "safe"])
    assert freed == 0
    assert outsider.exists()


def test_reset_reranker_clears_cached_model() -> None:
    import sidecar.rag.reranker as reranker

    reranker._RERANKER = object()
    reranker._RERANKER_DISABLED_UNTIL = 99.0
    reset_reranker()
    assert reranker._RERANKER is None
    assert reranker._RERANKER_DISABLED_UNTIL == 0.0


def test_reliability_handler_storage_rpc(
    app_data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from config import config

    _write_bytes(app_data / "hf_hub" / "m.bin", 7)
    ws = tmp_path / "vault"
    ws.mkdir()
    monkeypatch.setattr(config, "workspace_path", str(ws))
    handler = ReliabilityHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))
    usage = handler._get_storage_usage({})
    assert usage["success"] is True
    assert usage["total_bytes"] == 7
    cleared = handler._clear_storage({"targets": ["hf_hub"]})
    assert cleared["success"] is True
    assert cleared["total_bytes"] == 0
