"""CLI agent 多轮会话状态（按 agent + 工作区维度）。"""

from __future__ import annotations

from pathlib import Path

_sessions: set[str] = set()


def session_key(agent_id: str, workspace: str) -> str:
    agent = (agent_id or "").strip()
    ws = str(Path(workspace).expanduser().resolve())
    return f"{agent}::{ws}"


def has_session(agent_id: str, workspace: str) -> bool:
    if not agent_id or not workspace:
        return False
    return session_key(agent_id, workspace) in _sessions


def mark_session(agent_id: str, workspace: str) -> None:
    if not agent_id or not workspace:
        return
    _sessions.add(session_key(agent_id, workspace))


def clear_session(agent_id: str, workspace: str) -> None:
    if not agent_id or not workspace:
        return
    _sessions.discard(session_key(agent_id, workspace))


def clear_workspace_sessions(workspace: str) -> int:
    if not workspace:
        return 0
    ws = str(Path(workspace).expanduser().resolve())
    suffix = f"::{ws}"
    doomed = [key for key in _sessions if key.endswith(suffix)]
    for key in doomed:
        _sessions.discard(key)
    return len(doomed)
