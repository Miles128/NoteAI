import contextlib
import json
import re
import threading
from pathlib import Path

from config import config
from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from sidecar.handlers.base import BaseHandler

try:
    import jieba  # noqa: F811
    import jieba.analyse  # noqa: F401

    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False


class RagHandler(BaseHandler):
    _rag_chat_lock = threading.Lock()
    _rag_build_lock = threading.Lock()

    @staticmethod
    def _rag_disabled_message() -> str:
        return "向量 RAG 未启用。请在 设置 → 小忆助手 中开启「向量 RAG 检索」"

    def _init_rag_index(self, params):
        if not config.rag_enabled:
            return {"success": False, "message": self._rag_disabled_message()}

        from sidecar.rag.retriever import rebuild_index

        workspace = params.get("workspace", config.workspace_path)

        if not self._rag_build_lock.acquire(blocking=False):
            return {"success": False, "message": "索引构建正在进行中"}

        def build():
            try:
                self._send_progress("rag-index-progress", 0, "正在扫描文件...")

                def progress_cb(cur, tot, msg):
                    if tot <= 0:
                        pct = 5
                    else:
                        pct = min(95, max(5, int(cur / tot * 100)))
                    self._send_progress("rag-index-progress", pct, msg)
                    # Also flush stdout explicitly in case buffering delays UI updates
                    import sys

                    sys.stdout.flush()

                result = rebuild_index(progress_callback=progress_cb)

                if result.get("success") is False:
                    self._send_response(
                        {
                            "id": "event",
                            "result": {
                                "type": "rag_index_built",
                                "success": False,
                                "message": result.get("message", "索引构建失败"),
                            },
                        }
                    )
                else:
                    self._send_response(
                        {
                            "id": "event",
                            "result": {
                                "type": "rag_index_built",
                                "success": True,
                                "indexed": result.get("chunk_count", 0),
                            },
                        }
                    )
            except Exception as e:
                self._send_response(
                    {"id": "event", "result": {"type": "rag_index_built", "success": False, "message": str(e)}}
                )
            finally:
                self._rag_build_lock.release()

        t = threading.Thread(target=build, daemon=True)
        t.start()
        return {"success": True, "status": "started"}

    @staticmethod
    def _error_state_path():
        ws = config.workspace_path or ""
        p = Path(ws) / WORKSPACE_APP_FOLDER / RAG_INDEX_FOLDER / "error_state.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)

    @staticmethod
    def _check_error_reset():
        import time

        try:
            ep = RagHandler._error_state_path()
            data = json.loads(Path(ep).read_text(encoding="utf-8"))
            ts = data.get("ts", 0)
            if time.time() - ts < 180:
                return data.get("msg", ""), True
            Path(ep).unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return None, False

    @staticmethod
    def _clear_error_reset():
        with contextlib.suppress(OSError):
            Path(RagHandler._error_state_path()).unlink(missing_ok=True)

    @staticmethod
    def _record_error(msg):
        import time

        with contextlib.suppress(OSError):
            Path(RagHandler._error_state_path()).write_text(
                json.dumps({"ts": time.time(), "msg": msg}, ensure_ascii=False), encoding="utf-8"
            )

    def _rag_add_chunks(self, params):
        if not config.rag_enabled:
            return {"success": False, "message": self._rag_disabled_message()}

        file_path = params.get("file_path", "")
        if not file_path:
            return {"success": False, "message": "未指定文件路径"}

        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        from sidecar.rag.chunker import chunk_file
        from sidecar.rag.embedder import encode_documents
        from sidecar.rag.index import add_chunks

        try:
            text = Path(full_path).read_text(encoding="utf-8")
            chunks = chunk_file(full_path, text)
            if not chunks:
                return {"success": False, "message": "文件无可索引内容"}
            embeddings = encode_documents([c["content"] for c in chunks])
            add_chunks(workspace, chunks, embeddings)
            return {"success": True, "message": f"已添加 {len(chunks)} 个文本块"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _rag_remove_chunks(self, params):
        if not config.rag_enabled:
            return {"success": True}

        file_path = params.get("file_path", "")
        if not file_path:
            return {"success": False, "message": "未指定文件路径"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        from sidecar.rag.index import delete_by_file

        try:
            delete_by_file(workspace, file_path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _emit_rag_error(self, message: str) -> None:
        self._send_response(
            {
                "id": "event",
                "result": {"type": "rag_error", "message": message},
            }
        )

    def _fail_rag(self, message: str) -> dict:
        self._emit_rag_error(message)
        return {"success": False, "message": message, "error_emitted": True}

    def _rag_chat(self, params):
        question = (params.get("question") or "").strip()
        if not question:
            return {"success": False, "message": "问题不能为空"}

        if not self._rag_chat_lock.acquire(blocking=False):
            return {"success": False, "message": "已有对话正在进行，请稍候"}

        use_vector_rag = config.rag_enabled

        def _worker() -> None:
            try:
                result = self._do_rag_chat_inner(params, use_vector_rag=use_vector_rag)
                if isinstance(result, dict) and not result.get("success", True):
                    if not result.get("error_emitted"):
                        self._emit_rag_error(result.get("message", "请求失败"))
            except Exception as e:
                RagHandler._record_error(str(e))
                self._emit_rag_error(str(e))
            finally:
                self._rag_chat_lock.release()

        threading.Thread(target=_worker, daemon=True).start()
        return {"success": True, "started": True}

    def _rag_clear_memory(self, params):
        from sidecar.rag.memory import save_short_memory

        save_short_memory("")
        return {"success": True}

    def _do_rag_chat_inner(self, params, *, use_vector_rag: bool = True):
        from prompts import RAG_CHAT_PROMPT
        from sidecar.rag.memory import load_short_memory, save_short_memory
        from utils.llm_utils import APIConfigError, call_llm_raw_stream, check_api_config

        if use_vector_rag:
            from sidecar.rag.retriever import retrieve as search_fn
        else:
            from sidecar.classic_retriever import retrieve as search_fn

        question = params.get("question", "").strip()
        if not question:
            return {"success": False, "message": "问题不能为空"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        err_msg, has_recent_error = RagHandler._check_error_reset()
        if has_recent_error:
            return {"success": False, "message": f"[冷却] {err_msg}"}

        try:
            is_valid, error_msg = check_api_config()
            if not is_valid:
                return {"success": False, "message": error_msg}
        except APIConfigError as e:
            return {"success": False, "message": str(e)}

        topics = params.get("topics") or None
        tags = params.get("tags") or None

        try:
            if use_vector_rag:
                hyde_question = self._generate_hyde(question)
                search_results = search_fn(hyde_question, topics=topics, tags=tags)
                if not search_results:
                    search_results = search_fn(question, topics=topics, tags=tags)
            else:
                search_results = search_fn(question, topics=topics, tags=tags)
        except Exception as e:
            RagHandler._record_error(f"检索失败: {e}")
            return self._fail_rag(f"检索失败: {e}")

        def _send_tool_event(payload: dict) -> None:
            self._send_response({"id": "event", "result": payload})

        from sidecar.agent_runner import run_readonly_tool_prefetch

        tool_context = run_readonly_tool_prefetch(question, send_event=_send_tool_event)

        context_parts = []
        citations = []
        for r in search_results:
            body = (r.get("content") or "").strip()
            if not body:
                continue
            label = r.get("source_label") or r.get("file_name") or r.get("file_path", "")
            idx = len(context_parts) + 1
            context_parts.append(f"[{idx}] {label}\n{body}")
            citations.append(
                {
                    "index": idx,
                    "file_path": r.get("file_path", ""),
                    "file_name": r.get("file_name") or Path(r.get("file_path", "")).stem,
                    "source_label": r.get("source_label") or "",
                    "section_title": r.get("section_title") or "",
                    "topic": r.get("topic") or "",
                }
            )
        context = "\n\n".join(context_parts)
        if tool_context:
            context = (context + "\n\n" + tool_context).strip() if context else tool_context

        history = load_short_memory() or ""
        compressed = self._extractive_compress(history)

        prompt = RAG_CHAT_PROMPT.format(
            context=context,
            history=compressed if compressed else "无历史对话",
            question=question,
        )

        assistant_response = ""

        def on_token(token):
            self._send_response(
                {
                    "id": "event",
                    "result": {
                        "type": "rag_chat_chunk",
                        "token": token,
                    },
                }
            )

        try:
            assistant_response = call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=on_token)
        except APIConfigError as e:
            RagHandler._record_error(f"LLM调用失败: {e}")
            return self._fail_rag(str(e))
        except Exception as e:
            RagHandler._record_error(f"LLM错误: {e}")
            return self._fail_rag(str(e))

        if not assistant_response.strip():
            return self._fail_rag("AI 未生成回复")

        from sidecar.archive_wiki import parse_save_suggestion

        display_answer, suggest_save_note = parse_save_suggestion(assistant_response)

        if not display_answer.strip():
            return self._fail_rag("AI 未生成回复")

        RagHandler._clear_error_reset()

        updated_history = (
            f"{history}\n用户: {question}\n助手: {display_answer}"
            if history
            else f"用户: {question}\n助手: {display_answer}"
        )
        save_short_memory(updated_history)

        from sidecar.rag.memory import update_long_memory

        try:
            update_long_memory(question)
        except Exception:
            pass

        self._send_response(
            {
                "id": "event",
                "result": {
                    "type": "rag_chat_done",
                    "answer": display_answer,
                    "suggest_save_note": suggest_save_note,
                    "citations": citations,
                },
            }
        )
        return {"success": True, "suggest_save_note": suggest_save_note}

    def _generate_hyde(self, question):
        from prompts import RAG_HYDE_PROMPT
        from utils.llm_utils import APIConfigError, call_llm_raw, check_api_config

        try:
            is_valid, _ = check_api_config()
            if not is_valid:
                return question
        except APIConfigError:
            return question

        try:
            prompt = RAG_HYDE_PROMPT.format(question=question)
            result = call_llm_raw(prompt, temperature=0.1, max_tokens=300)
            return result.strip() or question
        except Exception:
            return question

    def _extractive_compress(self, older_history):
        if not older_history:
            return ""
        if isinstance(older_history, str):
            return older_history[:800]

        parts = []
        for h in older_history:
            role = "用户" if h["role"] == "user" else "助手"
            text = h["content"]
            if len(text) <= 80:
                parts.append(f"{role}: {text}")
                continue

            sentences = re.split(r"[。！？\n]", text)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 3]

            if not sentences:
                parts.append(f"{role}: {text[:80]}…")
                continue

            if len(sentences) == 1:
                first = sentences[0][:80]
            else:
                first = sentences[0][:60]
                last = sentences[-1][:60] if sentences[-1] != sentences[0] else ""
                if last:
                    first = first + "…" + last

            if not _HAS_JIEBA:
                parts.append(f"{role}: {first}…")
                continue

            keywords = jieba.analyse.extract_tags(text, topK=3, withWeight=False)
            kw_str = "、".join(keywords) if keywords else ""

            if kw_str:
                parts.append(f"{role}: {first}… [关键词: {kw_str}]")
            else:
                parts.append(f"{role}: {first}…")

        return "\n".join(parts)

    # _filter_history, _build_messages_with_history, _compress_history removed — unused dead code

    # _execute_single_action removed — LLM-generated code execution is a security risk

    def _rag_chat_with_actions(self, params):
        return self._rag_chat(params)

    def _rag_rebuild_index(self, params):
        """Manual full rebuild (settings / assistant); not run on app open."""
        return self._init_rag_index(params)

    def register_routes(self, router):
        router.register("init_rag_index", self._init_rag_index)
        router.register("rag_rebuild_index", self._rag_rebuild_index)
        router.register("rag_add_chunks", self._rag_add_chunks)
        router.register("rag_remove_chunks", self._rag_remove_chunks)
        router.register("rag_chat", self._rag_chat, async_mode=True)
        router.register("rag_chat_with_actions", self._rag_chat_with_actions, async_mode=True)
        router.register("rag_clear_memory", self._rag_clear_memory)
