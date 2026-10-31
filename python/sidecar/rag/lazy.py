"""Lazy module proxies so heavy extensions (zvec, bm25s) load only on first use.

These two C extensions cost ~20-25 MB of RSS at import time. Most sidecar
startup paths (config, lint, file listening) never touch retrieval, so the
import must not happen transitively. The proxy defers the real import to the
first attribute access and caches the module afterwards.

Thread safety: concurrent attribute access takes the lock once, then all
callers share the loaded module. If the target module is missing, the import
error raises on first attribute access rather than at startup.
"""

from __future__ import annotations

import importlib
import threading

__all__ = ["lazy_import"]


class _LazyModule:
    def __init__(self, name: str) -> None:
        self._name = name
        self._module = None
        self._lock = threading.Lock()

    def __getattr__(self, item: str):
        module = self._module
        if module is None:
            with self._lock:
                if self._module is None:
                    module = importlib.import_module(self._name)
                    self._module = module
                else:
                    module = self._module
        return getattr(module, item)


def lazy_import(name: str) -> _LazyModule:
    return _LazyModule(name)
