from pathlib import Path

from sidecar.cli_agent.agents.opencode import OpenCodeAgent


def test_opencode_enrich_prompt_includes_workspace_paths() -> None:
    ws = Path("/Users/test/My_Notes")
    enriched = OpenCodeAgent.enrich_prompt("分析 AI 产品经理之路", ws)
    assert "[NoteAI 工作区上下文]" in enriched
    assert str(ws) in enriched
    assert "Notes/AI产品经理之路" in enriched
    assert "vault_list_notes" in enriched
    assert "[用户任务]" in enriched
    assert enriched.endswith("分析 AI 产品经理之路\n")


def test_opencode_build_args_wraps_prompt() -> None:
    agent = OpenCodeAgent()
    ws = Path("/tmp/vault")
    args = agent.build_args("hello", ws, skip_permissions=True, continue_session=False)
    assert args[0] == "run"
    assert args[1] == "--dir"
    assert args[2] == str(ws)
    assert args[3] == "--dangerously-skip-permissions"
    assert "[NoteAI 工作区上下文]" in args[4]
    assert "hello" in args[4]
    assert "工作区安全边界" in args[4]


def test_opencode_saved_auth_grants_api_key(monkeypatch) -> None:
    """无环境变量时，已保存的 auth.json 即可满足凭据要求。"""
    agent = OpenCodeAgent()
    monkeypatch.setattr(agent, "check_api_keys", lambda: [])
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    fake_home = Path("/tmp/fake-opencode-home")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    assert agent._saved_auth_exists() is False
    assert agent.has_api_key() is False

    auth = fake_home / ".local" / "share" / "opencode" / "auth.json"
    auth.parent.mkdir(parents=True, exist_ok=True)
    auth.write_text("{}")
    assert agent._saved_auth_exists() is True
    assert agent.has_api_key() is True
