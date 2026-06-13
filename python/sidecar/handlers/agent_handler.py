import threading

from sidecar.agent_runner import run_agent_chat
from sidecar.handlers.base import BaseHandler
from sidecar.rag.memory import load_short_memory, save_short_memory, update_long_memory


class AgentHandler(BaseHandler):
    _agent_lock = threading.Lock()

    def _agent_chat(self, params):
        question = (params.get("question") or "").strip()
        agent_mode = bool(params.get("agent_mode", True))
        if not question:
            return {"success": False, "message": "问题不能为空"}

        if not self._agent_lock.acquire(blocking=False):
            return {"success": False, "message": "小忆还在处理上一题，请稍等一下"}

        history = load_short_memory() or ""

        def _worker() -> None:
            try:

                def send_event(payload: dict) -> None:
                    self._send_response({"id": "event", "result": payload})

                result = run_agent_chat(
                    question,
                    history=history,
                    agent_mode=agent_mode,
                    send_event=send_event,
                )
                if not result.get("success"):
                    self._send_response(
                        {
                            "id": "event",
                            "result": {
                                "type": "agent_error",
                                "message": result.get("message", "小忆没能完成这次请求"),
                            },
                        }
                    )
                    return

                answer = result.get("answer", "")
                updated = f"{history}\n用户: {question}\n助手: {answer}".strip()
                save_short_memory(updated[-3000:])
                update_long_memory(question)

                self._send_response(
                    {
                        "id": "event",
                        "result": {
                            "type": "agent_chat_done",
                            "answer": answer,
                            "tools": result.get("tools", []),
                        },
                    }
                )
            except Exception as e:
                self._send_response(
                    {
                        "id": "event",
                        "result": {"type": "agent_error", "message": str(e)},
                    }
                )
            finally:
                self._agent_lock.release()

        threading.Thread(target=_worker, daemon=True).start()
        return {"success": True, "started": True}

    def register_routes(self, router) -> None:
        router.register("agent_chat", self._agent_chat, async_mode=True)
