"""CLI Agent Handler — 桥接第三方 CLI agent（claude/opencode/codex/gemini/kimi）。

提供 RPC 路由：
1. list_cli_agents — 列出可用 agent 及安装状态
2. run_cli_agent — 启动 agent 处理用户请求（流式回传）
3. stop_cli_agent — 用户主动停止正在运行的 agent
"""

from __future__ import annotations

import threading

from sidecar import job_status
from sidecar.cli_agent.process_control import stop_active
from sidecar.cli_agent.session_store import clear_session
from sidecar.cli_agent_runner import list_available_agents, run_cli_agent
from sidecar.handlers.base import BaseHandler
from sidecar.vault_agents_md import generate_vault_agents_md


class CliAgentHandler(BaseHandler):
    _cli_agent_lock = threading.Lock()
    _current_process = None
    _current_lock = threading.Lock()

    def _list_agents(self, _params):
        """列出所有支持的 CLI agent 及安装状态。"""
        try:
            agents = list_available_agents()
            return {"success": True, "agents": agents}
        except Exception as e:
            return {"success": False, "message": f"列出 agent 失败: {e}"}

    def _run_agent(self, params):
        """启动 CLI agent 处理用户请求。"""
        agent_id = (params.get("agent_id") or "").strip()
        prompt = (params.get("prompt") or "").strip()
        workspace_path = params.get("workspace_path") or ""
        new_session = bool(params.get("new_session"))

        if not agent_id:
            return {"success": False, "message": "必须指定 agent_id"}
        if not prompt:
            return {"success": False, "message": "提示词不能为空"}

        if not self._cli_agent_lock.acquire(blocking=False):
            return {"success": False, "message": "上一个 CLI agent 任务还在运行，请稍等"}

        job_id = "cli_agent"
        job_status.start_job(
            job_id,
            kind="cli_agent",
            label=f"CLI agent: {agent_id}",
            message="CLI agent 已启动",
            metadata={"agent": agent_id},
            send_event=self._send_response,
        )

        def _worker() -> None:
            try:
                def send_event(payload: dict) -> None:
                    event_type = payload.get("type")
                    if event_type == "cli_agent_start":
                        job_status.update_job(
                            job_id,
                            progress=0.05,
                            message="CLI agent 正在运行",
                            metadata={"agent": agent_id},
                            send_event=self._send_response,
                        )
                    elif event_type == "cli_agent_output":
                        job_status.update_job(
                            job_id,
                            progress=0.5,
                            message="CLI agent 正在输出",
                            send_event=self._send_response,
                        )
                    elif event_type == "cli_agent_tool":
                        job_status.update_job(
                            job_id,
                            progress=0.6,
                            message=payload.get("name") or "CLI agent 正在调用工具",
                            send_event=self._send_response,
                        )
                    self._send_response({"id": "event", "result": payload})

                result = run_cli_agent(
                    agent_id=agent_id,
                    prompt=prompt,
                    workspace_path=workspace_path or None,
                    send_event=send_event,
                    new_session=new_session,
                )

                if not result.get("success"):
                    message = result.get("message", "CLI agent 执行失败")
                    if "用户已停止" not in message:
                        job_status.fail_job(job_id, message, send_event=self._send_response)
                        self._send_response({
                            "id": "event",
                            "result": {
                                "type": "cli_agent_error",
                                "agent": agent_id,
                                "message": message,
                            },
                        })
                    else:
                        job_status.cancel_job(job_id, message=message, send_event=self._send_response)
                    return

                job_status.complete_job(job_id, message="CLI agent 执行完成", send_event=self._send_response)
                self._send_response({
                    "id": "event",
                    "result": {
                        "type": "cli_agent_done",
                        "agent": agent_id,
                        "output": result.get("output", ""),
                    },
                })
            except Exception as e:
                job_status.fail_job(job_id, str(e), send_event=self._send_response)
                self._send_response({
                    "id": "event",
                    "result": {
                        "type": "cli_agent_error",
                        "agent": agent_id,
                        "message": str(e),
                    },
                })
            finally:
                self._cli_agent_lock.release()

        threading.Thread(target=_worker, daemon=True).start()
        return {"success": True, "started": True, "agent": agent_id}

    def _stop_agent(self, _params):
        """用户主动停止正在运行的 CLI agent。"""
        result = stop_active()
        if result.get("success"):
            job_status.cancel_job("cli_agent", message="用户已请求停止", send_event=self._send_response)
        return result

    def _clear_session(self, params):
        """清除 CLI agent 多轮会话状态（下次发送将开启新 session）。"""
        from config import config

        agent_id = (params.get("agent_id") or "").strip()
        workspace_path = (params.get("workspace_path") or config.workspace_path or "").strip()
        if not agent_id:
            return {"success": False, "message": "必须指定 agent_id"}
        if not workspace_path:
            return {"success": False, "message": "未设置工作区"}
        clear_session(agent_id, workspace_path)
        return {"success": True, "agent": agent_id}

    def _generate_agents_md(self, _params):
        """为当前工作区生成 AGENTS.md 文件。"""
        return generate_vault_agents_md()

    def register_routes(self, router) -> None:
        router.register("list_cli_agents", self._list_agents)
        router.register("run_cli_agent", self._run_agent, async_mode=True)
        router.register("stop_cli_agent", self._stop_agent)
        router.register("clear_cli_agent_session", self._clear_session)
        router.register("generate_vault_agents_md", self._generate_agents_md)
