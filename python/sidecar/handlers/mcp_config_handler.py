"""MCP Config Handler — 管理 NoteAI vault MCP server 在各 CLI agent 的注册。"""

from __future__ import annotations

from typing import Any

from sidecar.handlers.base import BaseHandler
from sidecar.mcp_config_manager import (
    get_mcp_status,
    register_mcp_server,
    unregister_mcp_server,
)


class McpConfigHandler(BaseHandler):
    def _register(self, params: dict[str, Any]) -> dict[str, Any]:
        """注册 NoteAI MCP server 到 CLI agent 配置文件。"""
        targets = params.get("targets")
        workspace_path = params.get("workspace_path") or ""
        return register_mcp_server(
            targets=targets,
            workspace_path=workspace_path or None,
        )

    def _unregister(self, params: dict[str, Any]) -> dict[str, Any]:
        """从 CLI agent 配置中移除 NoteAI MCP server。"""
        targets = params.get("targets")
        return unregister_mcp_server(targets=targets)

    def _status(self, _params: dict[str, Any]) -> dict[str, Any]:
        """返回各 CLI agent 的 MCP 注册状态。"""
        return {"success": True, "status": get_mcp_status()}

    def register_routes(self, router) -> None:
        router.register("register_mcp_server", self._register)
        router.register("unregister_mcp_server", self._unregister)
        router.register("get_mcp_status", self._status)
