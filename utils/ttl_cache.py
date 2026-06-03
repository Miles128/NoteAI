"""TTL-aware dict cache with LRU eviction — prevents unbounded memory growth."""

import time
import threading
from typing import Any, Optional


class TTLCache:
    """A thread-safe dict cache with per-entry TTL and optional max capacity.

    Each cached entry is a tuple of (value, expiry_time).  Expired entries are
    cleaned up on access (lazy) or via explicit :meth:`expire`.
    """

    __slots__ = ("_data", "_lock", "_ttl", "_max_size")

    def __init__(self, ttl: float = 300.0, max_size: int = 500):
        """*ttl* — seconds before an entry expires (default 5 minutes).
        *max_size* — maximum number of entries (oldest evicted when exceeded).
        """
        self._data: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if time.monotonic() > expiry:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        expiry = time.monotonic() + (ttl if ttl is not None else self._ttl)
        with self._lock:
            if key in self._data:
                del self._data[key]
            elif len(self._data) >= self._max_size:
                oldest = next(iter(self._data))
                del self._data[oldest]
            self._data[key] = (value, expiry)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def expire(self) -> int:
        """Remove all expired entries.  Returns count of removed items."""
        now = time.monotonic()
        removed = 0
        with self._lock:
            expired = [k for k, (_, exp) in self._data.items() if now > exp]
            for key in expired:
                del self._data[key]
                removed += 1
        return removed

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
