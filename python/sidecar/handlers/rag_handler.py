import contextlib
import json
import re
import threading
from pathlib import Path

from config import config, is_ignored_dir
from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from sidecar.handlers.base import BaseHandler

RAG_EXCLUDED_DIRS = {
    ".git",
    ".obsidian",
    ".trash",
    ".rag_index",
    ".ai_memory",
    WORKSPACE_APP_FOLDER,
    RAG_INDEX_FOLDER,
}

try:
    import jieba  # noqa: F811
    import jieba.analyse  # noqa: F401
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False


class RagHandler(BaseHandler):
    _rag_chat_lock = threading.Lock()
    _rag_build_lock = threading.Lock()

    def _init_rag_index(self, params):
        from sidecar.rag.chunker import chunk_file
        from sidecar.rag.embedder import encode_documents
        from sidecar.rag.index import build_index

        workspace = params.get("workspace", config.workspace_path)

        if not self._rag_build_lock.acquire(blocking=False):
            return {"success": False, "message": "索引构建正在进行中"}

        def build():
            try:
                self._send_progress("rag-index-progress", 0, "正在构建知识索引...")

                ws_path = Path(workspace)
                all_chunks = []
                file_names = []
                for md_file in ws_path.rglob("*.md"):
                    if md_file.name.startswith(".") or "wiki" in md_file.parts:
                        continue
                    rel_parts = md_file.relative_to(ws_path).parts
                    if any(part in RAG_EXCLUDED_DIRS or is_ignored_dir(part) for part in rel_parts):
                        continue
                    try:
                        text = md_file.read_text(encoding="utf-8")
                        chunks = chunk_file(str(md_file), text)
                        if chunks:
                            all_chunks.extend(chunks)
                            file_names.extend([str(md_file.relative_to(ws_path))] * len(chunks))
                    except Exception:
                        continue
                    self._send_progress("rag-index-progress", 30, f"已读取: {md_file.name}")

                if not all_chunks:
                    self._send_response({
                        "id": "event",
                        "result": {"type": "rag_index_built", "success": False, "message": "未找到可索引的内容"}
                    })
                    return

                self._send_progress("rag-index-progress", 40, "正在生成 Embedding...")
                embeddings = encode_documents([c["content"] for c in all_chunks])

                self._send_progress("rag-index-progress", 50, "正在构建索引...")
                build_index(workspace, all_chunks, embeddings,
                            progress_callback=lambda cur, tot, msg: self._send_progress("rag-index-progress", 50 + int(50 * cur / max(tot, 1)), msg))

                self._send_response({
                    "id": "event",
                    "result": {"type": "rag_index_built", "success": True, "indexed": len(all_chunks)}
                })
            except Exception as e:
                self._send_response({
                    "id": "event",
                    "result": {"type": "rag_index_built", "success": False, "message": str(e)}
                })
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
                json.dumps({"ts": time.time(), "msg": msg}, ensure_ascii=False),
                encoding="utf-8")

    def _rag_add_chunks(self, params):
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

    def _rag_chat(self, params):
        from prompts.rag_assistant import RAG_CHAT_PROMPT
        from sidecar.rag.memory import load_short_memory, save_short_memory
        from sidecar.rag.retriever import retrieve
        from utils.llm_utils import APIConfigError, call_llm_raw_stream, check_api_config

        with self._rag_chat_lock:
            return self._do_rag_chat_inner(
                params, retrieve, load_short_memory, save_short_memory,
                call_llm_raw_stream, check_api_config, APIConfigError, RAG_CHAT_PROMPT
            )

    def _rag_clear_memory(self, params):
        from sidecar.rag.memory import save_short_memory
        save_short_memory("")
        return {"success": True}

    def _do_rag_chat_inner(self, params, search_fn, load_memory_fn, save_memory_fn,
                           call_llm_raw_stream, check_api_config, APIConfigError,
                           RAG_CHAT_PROMPT):
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

        try:
            hyde_question = self._generate_hyde(question)
            search_results = search_fn(hyde_question)
            if not search_results:
                search_results = search_fn(question)
        except Exception as e:
            RagHandler._record_error(f"检索失败: {e}")
            return {"success": False, "message": f"检索失败: {e}"}

        context_parts = []
        for i, r in enumerate(search_results):
            context_parts.append(f"[{i + 1}] {r.get('file_name', r.get('file_path', ''))}\n{r.get('content', '')}")
        context = "\n\n".join(context_parts)

        history = load_memory_fn() or ""
        compressed = self._extractive_compress(history)

        prompt = RAG_CHAT_PROMPT.format(
            context=context,
            history=compressed if compressed else "无历史对话",
            question=question,
        )

        assistant_response = ""

        def on_token(token):
            self._send_response({
                "id": "event",
                "result": {
                    "type": "rag_chat_chunk",
                    "token": token,
                }
            })

        try:
            assistant_response = call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=on_token)
        except APIConfigError as e:
            RagHandler._record_error(f"LLM调用失败: {e}")
            self._send_response({
                "id": "event",
                "result": {"type": "rag_error", "message": str(e)}
            })
            return {"success": False, "message": str(e)}
        except Exception as e:
            RagHandler._record_error(f"LLM错误: {e}")
            self._send_response({
                "id": "event",
                "result": {"type": "rag_error", "message": str(e)}
            })
            return {"success": False, "message": str(e)}

        if not assistant_response.strip():
            return {"success": False, "message": "AI 未生成回复"}

        RagHandler._clear_error_reset()

        updated_history = f"{history}\n用户: {question}\n助手: {assistant_response}" if history else f"用户: {question}\n助手: {assistant_response}"
        save_memory_fn(updated_history)

        self._send_response({
            "id": "event",
            "result": {"type": "rag_chat_done"}
        })
        return {"success": True}

    def _generate_hyde(self, question):
        from prompts.rag_assistant import RAG_HYDE_PROMPT
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

            sentences = re.split(r'[。！？\n]', text)
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
        """Alias for _rag_chat — kept for backward-compatible RPC route."""
        return self._rag_chat(params)

    def register_routes(self, router):
        router.register("init_rag_index", self._init_rag_index)
        router.register("rag_add_chunks", self._rag_add_chunks)
        router.register("rag_remove_chunks", self._rag_remove_chunks)
        router.register("rag_chat", self._rag_chat, async_mode=True)
        router.register("rag_chat_with_actions", self._rag_chat_with_actions, async_mode=True)
        router.register("rag_clear_memory", self._rag_clear_memory)
