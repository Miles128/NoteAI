"""Tests for the local folder watcher (multi-source ingest)."""

import time
from pathlib import Path

import pytest

from config import config
from modules.folder_watcher import (
    FolderWatcher,
    add_watched_folder,
    collect_ingestible_files,
    is_supported_watch_file,
    load_watched_folders,
    remove_watched_folder,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir(parents=True)
    return d


# ── Subscription persistence ──


def test_add_and_list_watched_folder(workspace: Path) -> None:
    watched = workspace / "inbox"
    watched.mkdir()
    result = add_watched_folder(str(workspace), str(watched))
    assert result["success"] is True
    folders = load_watched_folders(str(workspace))
    assert len(folders) == 1
    assert folders[0]["path"] == str(watched)
    assert folders[0]["recursive"] is True


def test_add_watched_folder_missing_path(workspace: Path) -> None:
    result = add_watched_folder(str(workspace), "/no/such/dir")
    assert result["success"] is False


def test_add_watched_folder_duplicate(workspace: Path) -> None:
    watched = workspace / "inbox"
    watched.mkdir()
    add_watched_folder(str(workspace), str(watched))
    result = add_watched_folder(str(workspace), str(watched))
    assert result["success"] is False


def test_remove_watched_folder(workspace: Path) -> None:
    watched = workspace / "inbox"
    watched.mkdir()
    add_watched_folder(str(workspace), str(watched))
    result = remove_watched_folder(str(workspace), str(watched))
    assert result["success"] is True
    assert load_watched_folders(str(workspace)) == []


# ── File filtering / scanning ──


def test_is_supported_watch_file(workspace: Path) -> None:
    pdf = workspace / "a.pdf"
    pdf.write_text("x")
    hidden = workspace / ".hidden.pdf"
    hidden.write_text("x")
    exe = workspace / "a.exe"
    exe.write_text("x")
    assert is_supported_watch_file(str(pdf))
    assert not is_supported_watch_file(str(hidden))
    assert not is_supported_watch_file(str(exe))


def test_collect_ingestible_files(workspace: Path) -> None:
    sub = workspace / "sub"
    sub.mkdir()
    (workspace / "a.pdf").write_text("x")
    (workspace / "b.md").write_text("x")
    (workspace / "c.exe").write_text("x")
    (sub / "d.docx").write_text("x")
    flat = collect_ingestible_files(str(workspace), recursive=False)
    assert flat == [str(workspace / "a.pdf"), str(workspace / "b.md")]
    recursive = collect_ingestible_files(str(workspace), recursive=True)
    assert len(recursive) == 3


# ── FolderWatcher event handling ──


def test_folder_watcher_callback_on_created(tmp_path: Path) -> None:
    folder = tmp_path / "watch"
    folder.mkdir()
    collected = []
    watcher = FolderWatcher(on_files=lambda files: collected.extend(files))
    try:
        watcher.start([{"path": str(folder), "recursive": True, "enabled": True}])
        new_file = folder / "new.pdf"
        new_file.write_text("x")
        # 等待 watchdog 真实捕获到创建事件并回调
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not collected:
            time.sleep(0.05)
        assert collected == [str(new_file)]
    finally:
        watcher.stop()


def test_folder_watcher_ignores_unsupported_and_hidden(tmp_path: Path) -> None:
    folder = tmp_path / "watch"
    folder.mkdir()
    collected = []
    watcher = FolderWatcher(on_files=collected.append)
    watcher._queue_file(str(folder / "notes.exe"))
    watcher._queue_file(str(folder / ".hidden.pdf"))
    assert collected == []


def test_folder_watcher_start_skips_missing_dir(tmp_path: Path) -> None:
    watcher = FolderWatcher(on_files=lambda files: None)
    watcher.start([{"path": str(tmp_path / "nope"), "recursive": True, "enabled": True}])
    assert watcher._observer is None
    watcher.stop()


# ── Server-side ingest entrypoint ──


def test_server_handle_watched_folder_files(monkeypatch, tmp_path: Path) -> None:
    from sidecar.server import SidecarServer

    ws = tmp_path / "ws"
    ws.mkdir()
    config.workspace_path = str(ws)

    incoming = tmp_path / "incoming"
    incoming.mkdir()
    md = incoming / "note.md"
    md.write_text("# Hello\n\nbody", encoding="utf-8")
    txt = incoming / "draft.txt"
    txt.write_text("plain text content here for conversion", encoding="utf-8")

    server = SidecarServer()
    events = []
    monkeypatch.setattr(server, "_send_response", lambda resp: events.append(resp))

    class FakeConverter:
        def __init__(self):
            self.calls = []

        @staticmethod
        def get_supported_formats():
            return [".txt"]

        def convert_batch(self, files, output_path):
            self.calls.append((files, output_path))
            return [{"success": True, "source": files[0], "output_path": str(ws / "Notes" / "draft.md")}]

    server.file_converter = FakeConverter()
    server._handle_watched_folder_files([str(md), str(txt)])

    # .md 直接复制进 Notes 并补全 frontmatter
    notes_md = list((ws / "Notes").glob("note*.md"))
    assert len(notes_md) == 1
    content = notes_md[0].read_text(encoding="utf-8")
    assert "---" in content and "# Hello" in content
    # 非 .md 复制到 Raw 后交给转换器
    assert (ws / "Raw" / "draft.txt").exists()
    assert len(server.file_converter.calls) == 1
    # 推送完成事件
    assert events and events[0]["result"]["type"] == "folder_watch_complete"
    assert events[0]["result"]["data"]["imported"] == 2


def test_server_import_markdown_keeps_existing_frontmatter(monkeypatch, tmp_path: Path) -> None:
    from sidecar.server import SidecarServer

    ws = tmp_path / "ws"
    ws.mkdir()
    config.workspace_path = str(ws)

    incoming = tmp_path / "incoming"
    incoming.mkdir()
    md = incoming / "note.md"
    md.write_text('---\ntitle: "Keep Me"\n---\nbody', encoding="utf-8")

    server = SidecarServer()
    events = []
    monkeypatch.setattr(server, "_send_response", lambda resp: events.append(resp))
    server.file_converter = type("C", (), {"get_supported_formats": staticmethod(lambda: [])})()

    server._handle_watched_folder_files([str(md)])

    notes_md = list((ws / "Notes").glob("Keep Me.md"))
    assert len(notes_md) == 1
    assert 'title: "Keep Me"' in notes_md[0].read_text(encoding="utf-8")
