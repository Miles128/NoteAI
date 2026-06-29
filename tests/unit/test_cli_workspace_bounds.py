import json
from pathlib import Path

from sidecar.cli_agent.agents.codex import CodexAgent
from sidecar.cli_agent.agents.opencode import OpenCodeAgent
from sidecar.cli_agent.workspace_bounds import (
    append_workspace_boundary,
    apply_workspace_bounds_env,
    boundary_block,
)


def test_boundary_block_contains_workspace() -> None:
    ws = Path("/tmp/my-vault")
    text = boundary_block(ws)
    assert "工作区安全边界" in text
    assert str(ws) in text
    assert "禁止访问或修改工作区外" in text


def test_append_workspace_boundary_continue_is_short() -> None:
    ws = Path("/tmp/vault")
    out = append_workspace_boundary("继续", ws, continue_session=True)
    assert "继续" in out
    assert "仅限工作区" in out
    assert "禁止访问" not in out


def test_opencode_env_sets_config_content() -> None:
    ws = Path("/tmp/vault")
    env = apply_workspace_bounds_env({}, "opencode", ws)
    assert "OPENCODE_CONFIG_CONTENT" in env
    parsed = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert parsed["permission"]["external_directory"] == "deny"


def test_opencode_build_args_includes_dir_and_boundary() -> None:
    agent = OpenCodeAgent()
    ws = Path("/tmp/vault")
    args = agent.build_args("hello", ws, continue_session=False)
    assert args[0:2] == ["run", "--dir"]
    assert args[2] == str(ws)
    assert boundary_block(ws) in args[-1]


def test_codex_uses_workspace_write_sandbox() -> None:
    agent = CodexAgent()
    ws = Path("/tmp/vault")
    args = agent.build_args("task", ws, continue_session=False)
    assert args[:5] == ["exec", "--sandbox", "workspace-write", "-C", str(ws)]
    assert boundary_block(ws) in args[-1]


def test_codex_resume_keeps_sandbox() -> None:
    agent = CodexAgent()
    ws = Path("/tmp/vault")
    args = agent.build_args("next", ws, continue_session=True)
    assert "resume" in args
    assert "--sandbox" in args
    assert "-C" in args
