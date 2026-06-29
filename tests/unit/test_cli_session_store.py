from pathlib import Path

from sidecar.cli_agent.agents.codex import CodexAgent
from sidecar.cli_agent.agents.opencode import OpenCodeAgent
from sidecar.cli_agent.session_store import (
    clear_session,
    has_session,
    mark_session,
    session_key,
)


def test_session_key_normalizes_workspace() -> None:
    key_a = session_key("opencode", "/tmp/vault")
    key_b = session_key("opencode", "/tmp/vault/")
    assert key_a == key_b


def test_session_store_roundtrip() -> None:
    ws = "/tmp/noteai-session-test"
    clear_session("opencode", ws)
    assert not has_session("opencode", ws)
    mark_session("opencode", ws)
    assert has_session("opencode", ws)
    clear_session("opencode", ws)
    assert not has_session("opencode", ws)


def test_opencode_continue_uses_flag_and_raw_prompt() -> None:
    agent = OpenCodeAgent()
    ws = Path("/tmp/vault")
    args = agent.build_args("follow up", ws, skip_permissions=True, continue_session=True)
    assert args[:4] == ["run", "--dir", str(ws), "--dangerously-skip-permissions"]
    assert args[4] == "-c"
    assert "follow up" in args[5]
    assert "[NoteAI 工作区上下文]" not in args[5]
    assert "仅限工作区" in args[5]


def test_codex_continue_uses_exec_resume() -> None:
    agent = CodexAgent()
    ws = Path("/tmp/vault")
    args = agent.build_args("next", ws, continue_session=True)
    assert args[:5] == ["exec", "--sandbox", "workspace-write", "-C", str(ws)]
    assert args[5:8] == ["resume", "--last", args[-1]]
