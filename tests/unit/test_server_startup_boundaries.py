from sidecar.server import SidecarServer


def test_start_does_not_schedule_rss_polling(monkeypatch) -> None:
    server = SidecarServer()
    calls = []
    monkeypatch.setattr(server, "_start_workspace_watcher", lambda: calls.append("watcher"))
    monkeypatch.setattr(server, "_startup_sync", lambda: calls.append("sync"))

    server.start()

    assert calls == ["watcher", "sync"]
    assert not hasattr(server, "_rss_poll_timer")
