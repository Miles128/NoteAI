"""CLI Agent 桥接模块（兼容入口）。

具体实现已迁移到 sidecar/cli_agent/ 包，本文件仅保留旧版公开 API：
- list_available_agents()
- run_cli_agent()
"""

from __future__ import annotations

from sidecar.cli_agent import list_available_agents, run_cli_agent

__all__ = ["list_available_agents", "run_cli_agent"]
