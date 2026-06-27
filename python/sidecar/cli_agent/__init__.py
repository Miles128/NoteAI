"""CLI agent 桥接包。

对外统一入口：
- list_available_agents()
- run_cli_agent()

新增 agent 时只需在 agents/ 下继承 BaseCliAgent 并在 registry 中注册。
"""

from __future__ import annotations

from sidecar.cli_agent.base import AgentResult, BaseCliAgent, EventEmitter
from sidecar.cli_agent.registry import (
    AgentRegistry,
    get_registry,
    list_available_agents,
    run_cli_agent,
)

__all__ = [
    "AgentResult",
    "BaseCliAgent",
    "EventEmitter",
    "AgentRegistry",
    "get_registry",
    "list_available_agents",
    "run_cli_agent",
]
