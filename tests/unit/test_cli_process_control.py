"""Tests for CLI process control and timeout warnings."""

from __future__ import annotations

import subprocess
import sys
import time

from sidecar.cli_agent.process_control import TimeoutWatcher, clear, register, stop_active


def test_timeout_watcher_emits_warning_without_killing() -> None:
    events: list[dict] = []
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(3); print('done')"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    handle = register(proc, "test", "Test Agent")
    watcher = TimeoutWatcher(handle, idle_timeout_s=0.2, total_timeout_s=999, emit=events.append)
    watcher.start()
    try:
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            watcher.note_output()
        proc.wait(timeout=5)
    finally:
        clear(handle)

    assert watcher.kill_reason is None
    assert any(e.get("type") == "cli_agent_timeout_warning" and e.get("kind") == "idle" for e in events)


def test_stop_active_kills_process() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    handle = register(proc, "test", "Test Agent")
    watcher = TimeoutWatcher(handle, idle_timeout_s=999, total_timeout_s=999, emit=None)
    watcher.start()
    try:
        result = stop_active()
        assert result["success"] is True
        proc.wait(timeout=5)
        assert handle.stop_event.is_set()
    finally:
        clear(handle)
