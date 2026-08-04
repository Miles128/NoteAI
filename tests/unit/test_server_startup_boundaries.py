from sidecar.server import SidecarServer


def test_start_schedules_rss_polling(monkeypatch) -> None:
    server = SidecarServer()
    calls = []
    monkeypatch.setattr(server, "_start_workspace_watcher", lambda: calls.append("watcher"))
    monkeypatch.setattr(server, "_startup_sync", lambda: calls.append("sync"))
    monkeypatch.setattr(server, "_start_rss_scheduler", lambda: calls.append("rss_scheduler"))

    server.start()

    assert calls == ["watcher", "sync", "rss_scheduler"]


def test_auto_convert_uses_notes_output_directory(monkeypatch, tmp_path) -> None:
    server = SidecarServer()
    calls: list[tuple[str, str, str | None]] = []

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self) -> None:
            self.target()

    class Converter:
        def convert_file(self, source: str, output_dir: str, *, raw_path: str | None = None) -> dict:
            calls.append((source, output_dir, raw_path))
            return {"success": False}

    monkeypatch.setattr("sidecar.server.threading.Thread", ImmediateThread)
    monkeypatch.setattr("modules.file_converter.FileConverterManager", Converter)
    monkeypatch.setattr("sidecar.server.config.workspace_path", str(tmp_path))

    server._auto_convert_new_file("/incoming/report.pdf")

    assert calls == [("/incoming/report.pdf", str(tmp_path / "Notes"), str(tmp_path / "Raw"))]


def test_auto_convert_does_not_process_generated_markdown_twice(monkeypatch, tmp_path) -> None:
    server = SidecarServer()
    processed: list[str] = []

    class ImmediateThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self) -> None:
            self.target()

    class Converter:
        def convert_file(self, _source: str, _output_dir: str, *, raw_path: str | None = None) -> dict:
            assert raw_path == str(tmp_path / "Raw")
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


def test_startup_sync_schedules_non_destructive_organization_lint(monkeypatch, tmp_path) -> None:
    server = SidecarServer()
    started: list[tuple[str, object, dict]] = []

    monkeypatch.setattr("sidecar.server.config.workspace_path", str(tmp_path))
    monkeypatch.setattr("sidecar.server.config.rag_enabled", False)
    monkeypatch.setattr("sidecar.workspace_meta.merge_meta_docs_into_project_rules", lambda _ws: None)
    monkeypatch.setattr("utils.topic_assigner.sync_all_folder_topics", lambda _ws: None)
    monkeypatch.setattr("sidecar.kb_lint.auto_fix_broken_links", lambda _ws: None)
    monkeypatch.setattr("sidecar.workspace_rules.needs_workspace_rules_setup", lambda _ws: True)
    monkeypatch.setattr(server, "_send_response", lambda _event: None)
    monkeypatch.setattr(
        server,
        "_start_task",
        lambda name, target, **kwargs: started.append((name, target, kwargs)) or True,
    )

    server._startup_sync()

    lint = next(item for item in started if item[0] == "kb_startup_lint")
    assert lint[1] == server._run_startup_lint
    assert lint[2]["kind"] == "lint"


def test_startup_lint_is_non_destructive_and_refreshes_inbox(monkeypatch) -> None:
    server = SidecarServer()
    calls: list[dict] = []
    events: list[dict] = []
    monkeypatch.setattr("sidecar.kb_lint.run_kb_lint", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(server, "_send_response", events.append)

    server._run_startup_lint()

    assert calls == [{"auto_repair": False, "auto_refresh_surveys": False}]
    assert events[-1]["result"]["type"] == "workspace_files_changed"
