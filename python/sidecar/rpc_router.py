"""Lightweight JSON-RPC router for noteai sidecar. Supports sync and async handlers."""

import re
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from utils.error_codes import ErrorCode, NoteAIError, make_error
from utils.logger import logger


def _sanitize_error_message(message: str) -> str:
    """Remove absolute paths and home directory hints from RPC error messages."""
    if not message:
        return message
    home = str(Path.home())
    workspace = ""
    try:
        from config import config

        workspace = (config.workspace_path or "").strip()
    except Exception:
        workspace = ""
    for prefix in [workspace, home]:
        if prefix:
            message = message.replace(prefix, "<workspace>" if prefix == workspace else "<home>")
    # Collapse repeated placeholders
    message = re.sub(r"(<workspace>)+", "<workspace>", message)
    message = re.sub(r"(<home>)+", "<home>", message)
    return message


class RpcHandler:
    __slots__ = ("fn", "async_mode")

    def __init__(self, fn: Callable, async_mode: bool = False):
        self.fn = fn
        self.async_mode = async_mode


class RpcRouter:
    _MAX_WORKERS = 8

    def __init__(self, send_response: Callable[[dict], None] | None = None):
        self._handlers: dict[str, RpcHandler] = {}
        self.send_response = send_response
        self._executor = ThreadPoolExecutor(max_workers=self._MAX_WORKERS)

    def register(self, method: str, handler: Callable, *, async_mode: bool = False) -> None:
        self._handlers[method] = RpcHandler(handler, async_mode=async_mode)

    def handle(self, request: dict, extra_ctx: dict | None = None) -> None:
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id", "")

        handler = self._handlers.get(method)
        if handler is None:
            err = make_error(ErrorCode.METHOD_NOT_FOUND, f"Unknown method: {method}")
            self._send_error(req_id, err)
            return

        def _run():
            try:
                result = handler.fn(params)
                self._send_ok(req_id, result)
            except NoteAIError as e:
                err = make_error(e.code, _sanitize_error_message(e.message), details=e.details)
                self._send_error(req_id, err)
            except Exception as e:
                logger.error(f"[ERROR] {method}: {e}\n{traceback.format_exc()}")
                err = make_error(
                    ErrorCode.INTERNAL_ERROR,
                    _sanitize_error_message(str(e) or ErrorCode.INTERNAL_ERROR.value),
                )
                self._send_error(req_id, err)

        # Submit all handlers (sync and async) to the thread pool so the
        # stdin read loop in main() is never blocked by a slow handler.
        self._executor.submit(_run)

    def _send_ok(self, req_id: str, result: Any) -> None:
        if self.send_response is not None:
            self.send_response({"id": req_id, "result": result})

    def _send_error(self, req_id: str, error: dict | str) -> None:
        if self.send_response is not None:
            if isinstance(error, str):
                err = make_error(ErrorCode.INTERNAL_ERROR, error)
            else:
                err = error
            self.send_response({"id": req_id, "error": err})

    @property
    def methods(self):
        return list(self._handlers.keys())

    def shutdown(self, wait: bool = False):
        """Shutdown the thread pool used for async handlers."""
        try:
            self._executor.shutdown(wait=wait, cancel_futures=not wait)
        except Exception:
            pass
