"""CLI subprocess lifecycle: registration, user stop, timeout warnings."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

EmitFn = Callable[[dict[str, Any]], None]


@dataclass
class CliProcessHandle:
    proc: subprocess.Popen[str]
    agent_id: str
    display_name: str
    stop_event: threading.Event = field(default_factory=threading.Event)
    total_warned: bool = False
    idle_warned: bool = False


_registry_lock = threading.Lock()
_active: CliProcessHandle | None = None


def register(
    proc: subprocess.Popen[str],
    agent_id: str,
    display_name: str,
) -> CliProcessHandle:
    global _active
    handle = CliProcessHandle(
        proc=proc,
        agent_id=agent_id,
        display_name=display_name,
    )
    with _registry_lock:
        _active = handle
    return handle


def clear(handle: CliProcessHandle | None) -> None:
    global _active
    with _registry_lock:
        if handle is not None and _active is handle:
            _active = None


def stop_active() -> dict[str, Any]:
    with _registry_lock:
        handle = _active
    if handle is None or handle.proc.poll() is not None:
        return {"success": False, "message": "没有正在运行的 CLI Agent"}
    handle.stop_event.set()
    try:
        handle.proc.kill()
    except Exception:
        pass
    return {"success": True, "agent": handle.agent_id}


class TimeoutWatcher:
    """Monitor runtime; warn on thresholds but do not kill unless user stops."""

    def __init__(
        self,
        handle: CliProcessHandle,
        idle_timeout_s: float,
        total_timeout_s: float,
        emit: EmitFn | None,
    ) -> None:
        self.handle = handle
        self.idle_timeout_s = idle_timeout_s
        self.total_timeout_s = total_timeout_s
        self.emit = emit
        self.last_output_time = time.time()
        self.start_time = self.last_output_time
        self.kill_reason: str | None = None
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def note_output(self) -> None:
        self.last_output_time = time.time()
        self.handle.idle_warned = False

    def start(self) -> None:
        self._thread.start()

    def _loop(self) -> None:
        proc = self.handle.proc
        while proc.poll() is None:
            if self.handle.stop_event.is_set():
                self.kill_reason = "用户已停止"
                try:
                    proc.kill()
                except Exception:
                    pass
                return
            now = time.time()
            if (
                now - self.last_output_time > self.idle_timeout_s
                and not self.handle.idle_warned
            ):
                self.handle.idle_warned = True
                self._emit_warning("idle", int(self.idle_timeout_s))
            if (
                now - self.start_time > self.total_timeout_s
                and not self.handle.total_warned
            ):
                self.handle.total_warned = True
                self._emit_warning("total", int(self.total_timeout_s))
            time.sleep(1.0)

    def _emit_warning(self, kind: str, seconds: int) -> None:
        if not self.emit:
            return
        try:
            self.emit(
                {
                    "type": "cli_agent_timeout_warning",
                    "agent": self.handle.agent_id,
                    "kind": kind,
                    "seconds": seconds,
                }
            )
        except Exception:
            pass
