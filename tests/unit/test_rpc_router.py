"""Tests for RPC router."""

import time
from pathlib import Path

import pytest
from sidecar.rpc_router import RpcRouter, _sanitize_error_message


def _wait_for_responses(cap, count=1, timeout=2.0):
    """Poll until at least `count` responses arrive (handlers run async)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(cap.responses) >= count:
            return
        time.sleep(0.005)
    raise AssertionError(f"Timed out waiting for {count} response(s), got {len(cap.responses)}")


class TestRpcRouter:
    @pytest.fixture
    def captured(self):
        class Capture:
            def __init__(self):
                self.responses = []

            def send(self, resp):
                self.responses.append(resp)

        capture = Capture()
        router = RpcRouter(send_response=capture.send)
        return router, capture

    def test_known_sync_method(self, captured):
        router, cap = captured

        def echo(params):
            return {"msg": params.get("text", "")}

        router.register("echo", echo)
        router.handle({"id": "1", "method": "echo", "params": {"text": "hello"}})

        _wait_for_responses(cap)
        assert len(cap.responses) == 1
        assert cap.responses[0]["id"] == "1"
        assert cap.responses[0]["result"] == {"msg": "hello"}

    def test_unknown_method(self, captured):
        router, cap = captured
        router.handle({"id": "2", "method": "nonexistent", "params": {}})
        assert len(cap.responses) == 1
        assert "error" in cap.responses[0]
        err = cap.responses[0]["error"]
        assert isinstance(err, dict)
        assert err["code"] == "METHOD_NOT_FOUND"
        assert "Unknown method" in err["message"]

    def test_async_method(self, captured):
        import threading

        router, cap = captured
        event = threading.Event()

        def slow(params):
            event.set()
            return {"done": True}

        router.register("slow", slow, async_mode=True)
        router.handle({"id": "3", "method": "slow", "params": {}})
        event.wait(timeout=2)
        assert len(cap.responses) >= 1
        assert cap.responses[0]["result"] == {"done": True}

    def test_error_propagation(self, captured):
        router, cap = captured

        def failing(params):
            raise ValueError("boom")

        router.register("fail", failing)
        router.handle({"id": "4", "method": "fail", "params": {}})
        _wait_for_responses(cap)
        assert "error" in cap.responses[0]
        err = cap.responses[0]["error"]
        assert isinstance(err, dict)
        assert err["code"] == "INTERNAL_ERROR"
        assert "boom" in err["message"]

    def test_error_message_sanitizes_workspace_and_home_paths(self, captured, tmp_path):
        router, cap = captured
        ws = tmp_path / "workspace"
        ws.mkdir()
        home = Path.home()

        from config import config

        config.workspace_path = str(ws)

        def failing_with_paths(params):
            raise RuntimeError(f"Failed at {ws} under {home}")

        router.register("fail_paths", failing_with_paths)
        router.handle({"id": "5", "method": "fail_paths", "params": {}})
        _wait_for_responses(cap)
        assert "error" in cap.responses[0]
        err = cap.responses[0]["error"]
        assert isinstance(err, dict)
        msg = err["message"]
        assert str(ws) not in msg
        assert str(home) not in msg
        assert "<workspace>" in msg
        assert "<home>" in msg


def test_sanitize_error_message_replaces_paths():
    home = str(Path.home())
    raw = f"cannot read {home}/secret/workspace/file.txt"
    sanitized = _sanitize_error_message(raw)
    assert home not in sanitized
    assert "<home>" in sanitized
    assert "secret" in sanitized
