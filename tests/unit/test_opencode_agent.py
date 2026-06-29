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
