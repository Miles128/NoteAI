"""Lightweight JSON-RPC router for noteai sidecar. Supports sync and async handlers."""

import threading
from typing import Any, Callable, Dict, Optional


class RpcHandler:
    __slots__ = ("fn", "async_mode")

    def __init__(self, fn: Callable, async_mode: bool = False):
        self.fn = fn
        self.async_mode = async_mode


class RpcRouter:
    """Registers RPC method handlers and dispatches incoming requests."""

    def __init__(self, send_response: Optional[Callable[[dict], None]] = None):
        self._handlers: Dict[str, RpcHandler] = {}
        self.send_response = send_response

    def register(self, method: str, handler: Callable, *, async_mode: bool = False) -> None:
        self._handlers[method] = RpcHandler(handler, async_mode=async_mode)

    def handle(self, request: dict, extra_ctx: Optional[dict] = None) -> None:
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id", "")

        handler = self._handlers.get(method)
        if handler is None:
            self._send_error(req_id, f"Unknown method: {method}")
            return

        if handler.async_mode:
            def _run():
                try:
                    result = handler.fn(params)
                    self._send_ok(req_id, result)
                except Exception as e:
                    self._send_error(req_id, str(e))

            threading.Thread(target=_run, daemon=True).start()
        else:
            try:
                result = handler.fn(params)
                self._send_ok(req_id, result)
            except Exception as e:
                import traceback
                import sys
                sys.stderr.write(f"[ERROR] {method}: {e}\n")
                sys.stderr.write(traceback.format_exc())
                sys.stderr.flush()
                self._send_error(req_id, str(e))

    def _send_ok(self, req_id: str, result: Any) -> None:
        if self.send_response is not None:
            self.send_response({"id": req_id, "result": result})

    def _send_error(self, req_id: str, message: str) -> None:
        if self.send_response is not None:
            self.send_response({"id": req_id, "error": message})

    @property
    def methods(self):
        return list(self._handlers.keys())
