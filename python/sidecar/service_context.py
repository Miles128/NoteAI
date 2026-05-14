"""Service context — dependency injection container for noteai sidecar."""

from typing import Any


class ServiceContext:
    """Holds shared service instances and provides them to handlers.

    Replaces the global `from config import config` and `from utils.logger import logger`
    patterns with explicit dependency injection.  Handlers receive `ctx` and can access
    whatever they need without relying on module-level globals.
    """

    __slots__ = ("config", "logger", "cache", "services")

    def __init__(self, config: Any, logger: Any):
        self.config = config
        self.logger = logger
        self.cache: dict = {}
        self.services: dict = {}

    def register_service(self, name: str, instance: Any) -> None:
        self.services[name] = instance

    def get_service(self, name: str) -> Any:
        return self.services.get(name)
