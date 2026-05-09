import re
import sys
import threading

from config import config


class RagMixin:
    _rag_build_lock = threading.Lock()
    _rag_index_ready = False
    _session_chat_lock = threading.Lock()
    _MAX_SESSION_HISTORY = 20

    def __init__(self):
        self._session_chat_history = []

    @staticmethod
    def _is_simple_question(text):
        cleaned = re.sub(r'[^\w]', '', text)
        return len(cleaned) <= 10

    def _rag_progress_callback(self, current, total, message):
        pct = int(current / total * 100) if total > 0 else 0
        self._send_progress("rag-index", pct, message)

    def _rag_chat(self, params):
        question = params.get("question", "").strip()
        if not question:
            return {"success": False, "message": "问题不能为空"}

        from utils.llm_utils import check_api_config
        is_valid, error_msg = check_api_config()
        if not is_valid:
            return {"success": False, "message": error_msg}

        topics = params.get("topics") or None
        tags = params.get("tags") or None

        t = threading.Thread(target=self._do_rag_chat, args=(question, topics, tags), daemon=True)
        t.start()
        return {"success": True}

    def _do_rag_chat(self, question, topics, tags):
        from sidecar.rag.index import index_exists
        from sidecar.rag.retriever import retrieve, rebuild_index
        from sidecar.rag.memory import update_long_memory, build_memory_section
        from prompts.rag_assistant import ASSISTANT_PERSONA_PROMPT

        workspace = config.workspace_path
        if not workspace or not index_exists(workspace):
            if not self._rag_build_lock.acquire(blocking=False):
                self._send_response({"id": "event", "result": {"type": "rag_chat_chunk", "token": "索引正在构建中，请稍后再试..."}})
                self._send_response({"id": "event", "result": {"type": "rag_chat_done", "success": True, "has_context": False}})
                return

            try:
                result = rebuild_index(progress_callback=self._rag_progress_callback)
                self._send_response({"id": "event", "result": {"type": "rag_index_built", "data": result}})
                if result.get("success"):
                    RagMixin._rag_index_ready = True
                else:
                    self._send_response({"id": "event", "result": {"type": "rag_chat_chunk", "token": "索引构建失败: " + result.get("message", "未知错误")}})
                    self._send_response({"id": "event", "result": {"type": "rag_chat_done", "success": True, "has_context": False}})
                    return
            except Exception as e:
                sys.stderr.write(f"[rag_mixin] rebuild error: {e}\n")
                sys.stderr.flush()
                self._send_response({"id": "event", "result": {"type": "rag_chat_chunk", "token": "索引构建异常: " + str(e)}})
                self._send_response({"id": "event", "result": {"type": "rag_chat_done", "success": True, "has_context": False}})
                return
            finally:
                self._rag_build_lock.release()

        try:
            results = retrieve(question, topics=topics, tags=tags, progress_callback=self._rag_progress_callback)
        except Exception as e:
            sys.stderr.write(f"[rag_mixin] retrieve error: {e}\n")
            sys.stderr.flush()
            results = []

        has_context = bool(results)
        source_type = "knowledge_base"
        memory_section = build_memory_section()
        persona = ASSISTANT_PERSONA_PROMPT.strip()

        if has_context:
            context_parts = []
            for i, r in enumerate(results):
                source = r.get("file_path", "未知文件")
                section = r.get("section_title", "")
                loc = f"{source}" + (f" > {section}" if section else "")
                context_parts.append(f"[{i+1}] ({loc})\n{r['content']}")
            context = "\n\n".join(context_parts)

            from prompts.rag_assistant import RAG_ASSISTANT_PROMPT
            prompt = RAG_ASSISTANT_PROMPT.format(persona=persona, memory_section=memory_section, context=context, question=question)
        elif self._is_simple_question(question):
            source_type = "direct"
            from prompts.rag_assistant import RAG_ASSISTANT_NO_CONTEXT_PROMPT
            prompt = RAG_ASSISTANT_NO_CONTEXT_PROMPT.format(persona=persona, memory_section=memory_section, question=question)
        else:
            from sidecar.rag.web_search import web_search
            try:
                search_results = web_search(question)
            except Exception as e:
                sys.stderr.write(f"[rag_mixin] web search error: {e}\n")
                sys.stderr.flush()
                search_results = []

            if search_results:
                source_type = "web_search"
                web_parts = []
                for i, r in enumerate(search_results):
                    web_parts.append(f"[{i+1}] {r['title']}\n来源: {r['url']}\n{r['snippet']}")
                web_context = "\n\n".join(web_parts)

                from prompts.rag_assistant import RAG_ASSISTANT_WEB_PROMPT
                prompt = RAG_ASSISTANT_WEB_PROMPT.format(persona=persona, memory_section=memory_section, web_context=web_context, question=question)
            else:
                from prompts.rag_assistant import RAG_ASSISTANT_NO_CONTEXT_PROMPT
                prompt = RAG_ASSISTANT_NO_CONTEXT_PROMPT.format(persona=persona, memory_section=memory_section, question=question)

        from utils.llm_utils import create_llm

        llm = create_llm(temperature=0.3)
        messages = [{"role": "user", "content": prompt}]

        full_response = ""
        for chunk in llm.stream(messages):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_response += token
            self._send_response({"id": "event", "result": {"type": "rag_chat_chunk", "token": token}})

        with self._session_chat_lock:
            self._session_chat_history.append({"role": "user", "content": question})
            self._session_chat_history.append({"role": "assistant", "content": full_response})
            if len(self._session_chat_history) > self._MAX_SESSION_HISTORY:
                self._session_chat_history = self._session_chat_history[-self._MAX_SESSION_HISTORY:]

        self._send_response({"id": "event", "result": {"type": "rag_chat_done", "success": True, "has_context": has_context, "source_type": source_type}})

        threading.Thread(target=self._post_chat_memory_update, args=(question,), daemon=True).start()

    def _post_chat_memory_update(self, user_message):
        try:
            if "我" in user_message:
                from sidecar.rag.memory import update_long_memory
                update_long_memory(user_message)
        except Exception as e:
            sys.stderr.write(f"[rag_mixin] long memory update error: {e}\n")
            sys.stderr.flush()

        try:
            from sidecar.rag.memory import update_short_memory
            with self._session_chat_lock:
                history_snapshot = list(self._session_chat_history)
            update_short_memory(history_snapshot)
        except Exception as e:
            sys.stderr.write(f"[rag_mixin] short memory update error: {e}\n")
            sys.stderr.flush()

    def _rag_rebuild_index(self, params):
        if not self._rag_build_lock.acquire(blocking=False):
            return {"success": False, "message": "索引正在构建中"}

        def run():
            try:
                from sidecar.rag.retriever import rebuild_index
                result = rebuild_index(progress_callback=self._rag_progress_callback)
                self._send_response({"id": "event", "result": {"type": "rag_index_built", "data": result}})
                if result.get("success"):
                    RagMixin._rag_index_ready = True
            except Exception as e:
                sys.stderr.write(f"[rag_mixin] rebuild error: {e}\n")
                sys.stderr.flush()
                self._send_response({"id": "event", "result": {"type": "rag_index_built", "data": {"success": False, "message": str(e)}}})
            finally:
                self._rag_build_lock.release()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return {"success": True, "status": "started", "message": "索引构建已启动"}

    def _rag_incremental_update(self, params):
        file_path = params.get("file_path", "").strip()
        action = params.get("action", "update")
        if not file_path:
            return {"success": False, "message": "file_path 不能为空"}

        from sidecar.rag.retriever import incremental_update
        try:
            result = incremental_update(file_path, action=action)
            return result
        except Exception as e:
            return {"success": False, "message": str(e)}
