"""RAG chat streaming: token batching and per-session gates."""

from __future__ import annotations

import threading


class RagChatChunkBatcher:
    """流式回答 token 攒批：合并成整段 JSON 单次写 stdout。

    逐 token 发送时 2000 token 的回答 = 2000 次 write+flush+JSON 解析+前端事件；
    攒批后按定时器（50ms）或字符阈值（200）合并发送，网络与解析开销降一个量级。
    发送在锁外执行（锁内取数据），避免与 stdout 锁形成反向等待。
    """

    def __init__(self, send_response, *, flush_interval: float = 0.05, max_chars: int = 200):
        self._send_response = send_response
        self._interval = flush_interval
        self._max_chars = max_chars
        self._buffer: list[str] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._closed = False

    def append(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            if self._closed:
                return
            self._buffer.append(token)
            if sum(len(t) for t in self._buffer) >= self._max_chars:
                self._send_locked()
                return
            if self._timer is None:
                self._timer = threading.Timer(self._interval, self._flush_from_timer)
                self._timer.daemon = True
                self._timer.start()

    def _flush_from_timer(self) -> None:
        payload = self._take_payload()
        if payload:
            self._emit(payload)

    def _send_locked(self) -> None:
        payload = "".join(self._buffer)
        self._buffer.clear()
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._emit(payload)

    def _take_payload(self) -> str:
        with self._lock:
            self._timer = None
            if not self._buffer:
                return ""
            payload = "".join(self._buffer)
            self._buffer.clear()
            return payload

    def _emit(self, payload: str) -> None:
        self._send_response({"id": "event", "result": {"type": "rag_chat_chunk", "token": payload}})

    def flush(self) -> None:
        """流结束强制发送剩余 token 并停表。"""
        payload = self._take_payload()
        with self._lock:
            self._closed = True
        if payload:
            self._emit(payload)


class SessionGate:
    """按 session 的对话门禁：同会话串行、不同会话可并行。

    引用计数保证锁空闲即从字典移除，避免 session 锁无限累积。
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.users = 0
