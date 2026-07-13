from sidecar.server import SidecarServer


def test_start_does_not_schedule_rss_polling(monkeypatch) -> None:
    server = SidecarServer()
    calls = []
    monkeypatch.setattr(server, "_start_workspace_watcher", lambda: calls.append("watcher"))
    monkeypatch.setattr(server, "_startup_sync", lambda: calls.append("sync"))

    server.start()

    assert calls == ["watcher", "sync"]
    assert not hasattr(server, "_rss_poll_timer")


def test_auto_convert_uses_notes_output_directory(monkeypatch, tmp_path) -> None:
    server = SidecarServer()
    calls: list[tuple[str, str]] = []

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self) -> None:
            self.target()

    class Converter:
        def convert_file(self, source: str, output_dir: str) -> dict:
            calls.append((source, output_dir))
            return {"success": False}

    monkeypatch.setattr("sidecar.server.threading.Thread", ImmediateThread)
    monkeypatch.setattr("modules.file_converter.FileConverterManager", Converter)
    monkeypatch.setattr("sidecar.server.config.workspace_path", str(tmp_path))

    server._auto_convert_new_file("/incoming/report.pdf")

    assert calls == [("/incoming/report.pdf", str(tmp_path / "Notes"))]


def test_auto_convert_does_not_process_generated_markdown_twice(monkeypatch, tmp_path) -> None:
    server = SidecarServer()
    processed: list[str] = []

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self) -> None:
            self.target()

    class Converter:
        def convert_file(self, _source: str, _output_dir: str) -> dict:
            return {"success": True, "output_path": str(tmp_path / "Notes" / "report.md")}

    monkeypatch.setattr("sidecar.server.threading.Thread", ImmediateThread)
    monkeypatch.setattr("modules.file_converter.FileConverterManager", Converter)
    monkeypatch.setattr("sidecar.server.config.workspace_path", str(tmp_path))
    monkeypatch.setattr(server, "_auto_process_md_file", processed.append)
    monkeypatch.setattr(server, "_send_response", lambda _event: None)

    server._auto_convert_new_file("/incoming/report.pdf")

    assert processed == []


def test_auto_convert_deduplicates_inflight_source(monkeypatch, tmp_path) -> None:
    server = SidecarServer()
    queued = []

    class DeferredThread:
        def __init__(self, *, target, daemon):
            queued.append(target)

        def start(self) -> None:
            return None

    monkeypatch.setattr("sidecar.server.threading.Thread", DeferredThread)
    monkeypatch.setattr("sidecar.server.config.workspace_path", str(tmp_path))

    server._auto_convert_new_file("/incoming/report.pdf")
    server._auto_convert_new_file("/incoming/report.pdf")

    assert len(queued) == 1
