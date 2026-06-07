"""Service context — dependency injection container for noteai sidecar."""

from typing import Any


class ServiceContext:
    """Holds shared service instances and provides them to handlers.

    Replaces the global `from config import config` and `from utils.logger import logger`
    patterns with explicit dependency injection.  Handlers receive `ctx` and can access
    whatever they need without relying on module-level globals.
    """

    __slots__ = ("config", "logger")

    def __init__(self, config: Any, logger: Any):
        self.config = config
        self.logger = logger
