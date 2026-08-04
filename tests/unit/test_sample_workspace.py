"""Tests for the bundled sample workspace (first-run onboarding)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from sidecar import sample_workspace
from sidecar.handlers.workspace_handler import WorkspaceHandler

from config import config
from config.settings import workspace_manager


@pytest.fixture
def restore_workspace():
    previous = config.workspace_path
    yield
    config._set_attr("workspace_path", previous)


def test_bundled_sample_notes_exist() -> None:
    root = sample_workspace.sample_root()
    assert root.exists(), "sample_workspace resources must ship with the repo"
    assert sample_workspace.sample_note_count() >= 10
    notes = root / "Notes"
    assert notes.exists()
    readmes = list(notes.rglob("README.md"))
    assert readmes, "sample workspace should keep its README guide"


def test_create_sample_workspace_copies_notes(tmp_path: Path) -> None:
    target = tmp_path / "示例库"
    ok, message, path = sample_workspace.create_sample_workspace(str(target))
    assert ok, message
    assert Path(path) == target.resolve()
    copied = sorted(p.relative_to(target) for p in target.rglob("*.md"))
    bundled = sorted(
        p.relative_to(sample_workspace.sample_root()) for p in sample_workspace.sample_root().rglob("*.md")
    )
    assert copied == bundled
    # Subdirectory structure is preserved.
    assert any("AI 技术基础" in str(rel) for rel in copied)


def test_create_sample_workspace_rejects_non_empty_dir(tmp_path: Path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "keep.md").write_text("user data", encoding="utf-8")
    ok, message, _ = sample_workspace.create_sample_workspace(str(target))
    assert not ok
    assert "不为空" in message
    assert (target / "keep.md").read_text(encoding="utf-8") == "user data"


def test_default_target_appends_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    first = sample_workspace._default_target()
    assert first == tmp_path / "Documents" / sample_workspace.SAMPLE_WORKSPACE_NAME
    first.mkdir(parents=True)
    second = sample_workspace._default_target()
    assert second == tmp_path / "Documents" / f"{sample_workspace.SAMPLE_WORKSPACE_NAME} (2)"


def test_create_sample_workspace_rpc_activates_workspace(
    tmp_path: Path, restore_workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workspace_manager, "save_workspace", lambda path: (True, "ok"))
    watcher_calls: list[str] = []
    previewer = SimpleNamespace(workspace_path="")
    server = SimpleNamespace(
        _ctx=SimpleNamespace(config=config, logger=None),
        file_previewer=previewer,
        _setup_watcher=lambda path: watcher_calls.append(path),
        _invalidate_cache=lambda: None,
    )
    handler = WorkspaceHandler(server)

    result = handler._create_sample_workspace({"target_dir": str(tmp_path / "sample")})

    assert result["success"] is True
    assert result["sample"] is True
    workspace_path = result["workspace_path"]
    assert config.workspace_path == workspace_path
    assert previewer.workspace_path == workspace_path
    assert watcher_calls == [workspace_path]
    assert (Path(workspace_path) / "Notes").exists()
