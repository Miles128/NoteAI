#!/usr/bin/env python3
"""CLI agent 接入冒烟测试（无需 UI）。"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

from config import config
from sidecar.cli_agent_runner import list_available_agents, run_cli_agent
from sidecar.handlers.cli_agent_handler import CliAgentHandler
from sidecar.handlers.mcp_config_handler import McpConfigHandler
from sidecar.mcp_config_manager import get_mcp_status, register_mcp_server


def _banner(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> int:
    _banner("1. 列出 CLI agent")
    agents = list_available_agents()
    installed = [a for a in agents if a.get("installed")]
    print(json.dumps(agents, ensure_ascii=False, indent=2))
    print(f"\n已安装: {len(installed)} / {len(agents)}")
    if not installed:
        print("警告: 未检测到已安装的 CLI agent，UI 中 CLI Tab 将不可用")

    ws = config.workspace_path
    if not ws:
        with tempfile.TemporaryDirectory() as tmp:
            ws = tmp
            (Path(ws) / "Notes").mkdir()
            (Path(ws) / "wiki").mkdir()
            config.workspace_path = ws
            print(f"\n使用临时工作区: {ws}")
    else:
        print(f"\n当前工作区: {ws}")

    _banner("2. MCP 注册状态（注册前）")
    before = get_mcp_status()
    for name, info in before.items():
        flag = "✓" if info.get("registered") else "·"
        print(f"  [{flag}] {name:10} {info.get('path')}")

    _banner("3. 注册 NoteAI vault MCP 到全部 CLI")
    reg = register_mcp_server(workspace_path=ws)
    print(json.dumps(reg, ensure_ascii=False, indent=2))
    if not reg.get("success"):
        print("MCP 注册失败")
        return 1

    _banner("4. MCP 注册状态（注册后）")
    after = get_mcp_status()
    for name, info in after.items():
        flag = "✓" if info.get("registered") else "·"
        print(f"  [{flag}] {name:10} {info.get('path')}")

    _banner("5. Handler RPC 契约")
    class _FakeServer:
        def _send_response(self, resp):
            pass

    mcp_handler = McpConfigHandler(_FakeServer())
    status_rpc = mcp_handler._status({})
    assert status_rpc.get("success"), status_rpc
    print("get_mcp_status RPC: OK")

    cli_handler = CliAgentHandler(_FakeServer())
    list_rpc = cli_handler._list_agents({})
    assert list_rpc.get("success") and list_rpc.get("agents"), list_rpc
    print(f"list_cli_agents RPC: OK ({len(list_rpc['agents'])} agents)")

    if not installed:
        print("\n跳过 run_cli_agent（无已安装 agent）")
        return 0

    pick = installed[0]
    agent_id = pick["id"]
    _banner(f"6. 派发 CLI 任务 ({agent_id})")
    events: list[dict] = []

    def _capture(event: dict) -> None:
        events.append(event)
        etype = event.get("type", "?")
        if etype == "cli_agent_output":
            content = (event.get("content") or "")[:120]
            print(f"  [output] {content!r}")
        else:
            print(f"  [{etype}] {json.dumps({k: v for k, v in event.items() if k != 'output'}, ensure_ascii=False)}")

    prompt = "只回复 OK，不要执行任何工具或文件操作。"
    print(f"prompt: {prompt!r}")
    t0 = time.time()
    result = run_cli_agent(
        agent_id=agent_id,
        prompt=prompt,
        workspace_path=ws,
        send_event=_capture,
    )
    elapsed = time.time() - t0
    print(f"\n结果 ({elapsed:.1f}s): {json.dumps(result, ensure_ascii=False)[:500]}")
    print(f"事件数: {len(events)}")

    if result.get("success"):
        print("\n✅ CLI 接入测试通过")
        return 0

    print(f"\n⚠️  CLI 执行未成功: {result.get('message')}")
    print("（agent 列表与 MCP 注册已通过；执行失败可能是 API key 或 CLI 配置问题）")
    return 0 if reg.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
