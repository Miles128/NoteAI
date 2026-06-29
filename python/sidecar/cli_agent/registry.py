"""CLI agent 注册表：统一发现、列举与执行所有支持的 agent。"""

from __future__ import annotations

from typing import Any

from sidecar.cli_agent.agents.claude_mcp import ClaudeMcpAgent
from sidecar.cli_agent.agents.codex import CodexAgent
from sidecar.cli_agent.agents.gemini import GeminiAgent
from sidecar.cli_agent.agents.kimi import KimiAgent
from sidecar.cli_agent.agents.opencode import OpenCodeAgent
from sidecar.cli_agent.base import BaseCliAgent


class AgentRegistry:
    """CLI agent 注册表。

    所有支持的 agent 都在这里注册。新增 agent 时：
    1. 在 agents/ 下创建子类
    2. 在 _AGENTS 字典中注册

    Claude 默认走 MCP 模式（spawn Claude CLI + --mcp-config）。
    其余 agent 启动前也会自动注册 NoteAI vault MCP server。
    旧版直连实现仍保留在 agents/claude.py 中，需要时可手动注册。
    """

    _AGENTS: dict[str, type[BaseCliAgent]] = {
        ClaudeMcpAgent.agent_id: ClaudeMcpAgent,
        OpenCodeAgent.agent_id: OpenCodeAgent,
        CodexAgent.agent_id: CodexAgent,
        GeminiAgent.agent_id: GeminiAgent,
        KimiAgent.agent_id: KimiAgent,
    }

    def __init__(self) -> None:
        self._instances: dict[str, BaseCliAgent] = {}

    def _get(self, agent_id: str) -> BaseCliAgent | None:
        if agent_id not in self._instances:
            cls = self._AGENTS.get(agent_id)
            if cls is None:
                return None
            self._instances[agent_id] = cls()
        return self._instances[agent_id]

    def list_agents(self) -> list[dict[str, Any]]:
        """列出所有支持的 agent 及其安装状态。"""
        return [self._get(aid).info() for aid in self._AGENTS]

    def is_supported(self, agent_id: str) -> bool:
        return agent_id in self._AGENTS

    def run(
        self,
        agent_id: str,
        prompt: str,
        workspace_path: str | None = None,
        send_event: Any | None = None,
        skip_permissions: bool = True,
        *,
        new_session: bool = False,
    ) -> dict[str, Any]:
        """执行指定 agent。"""
        agent = self._get(agent_id)
        if agent is None:
            return {
                "success": False,
                "message": f"不支持的 agent: {agent_id}",
            }
        result = agent.run(
            prompt,
            workspace_path=workspace_path,
            send_event=send_event,
            skip_permissions=skip_permissions,
            new_session=new_session,
        )
        return result.to_dict()


# 全局注册表实例
_registry: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    """获取全局 AgentRegistry 单例。"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


def list_available_agents() -> list[dict[str, Any]]:
    """列出所有支持的 agent 及其安装状态。"""
    return get_registry().list_agents()


def run_cli_agent(
    agent_id: str,
    prompt: str,
    workspace_path: str | None = None,
    send_event: Any | None = None,
    skip_permissions: bool = True,
    *,
    new_session: bool = False,
) -> dict[str, Any]:
    """启动 CLI agent 处理用户请求。"""
    return get_registry().run(
        agent_id,
        prompt,
        workspace_path=workspace_path,
        send_event=send_event,
        skip_permissions=skip_permissions,
        new_session=new_session,
    )
