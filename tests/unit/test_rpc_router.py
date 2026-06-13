"""Tests for RPC router."""

import pytest
from sidecar.rpc_router import RpcRouter


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

        assert len(cap.responses) == 1
        assert cap.responses[0]["id"] == "1"
        assert cap.responses[0]["result"] == {"msg": "hello"}

    def test_unknown_method(self, captured):
        router, cap = captured
        router.handle({"id": "2", "method": "nonexistent", "params": {}})
        assert len(cap.responses) == 1
        assert "error" in cap.responses[0]
        assert "Unknown method" in cap.responses[0]["error"]

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
        assert "error" in cap.responses[0]
        assert "boom" in cap.responses[0]["error"]
