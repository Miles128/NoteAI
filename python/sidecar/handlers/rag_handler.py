import contextlib
import json
import re
import threading
from pathlib import Path

from config import config
from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from sidecar import job_status
from sidecar.handlers.base import BaseHandler
from utils.logger import logger

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
        return "向量 RAG 未启用。请在 设置 → RAG 检索 中开启「向量 RAG 检索」"

    def _init_rag_index(self, params):
        if not config.rag_enabled:
            return {"success": False, "message": self._rag_disabled_message()}

        from sidecar.rag.retriever import rebuild_index

        workspace = params.get("workspace", config.workspace_path)

        if not self._rag_build_lock.acquire(blocking=False):
            return {"success": False, "message": "索引构建正在进行中"}

        job_id = "rag-index-progress"
        job_status.start_job(
            job_id,
            kind="rag_index",
            label="RAG index",
            message="正在扫描文件...",
            send_event=self._send_response,
        )

        def build():
            try:
                RagHandler._clear_error_reset()
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

                result = rebuild_index(progress_callback=progress_cb, workspace=workspace)

                if result.get("success") is False:
                    job_status.fail_job(
                        job_id,
                        result.get("message", "索引构建失败"),
                        send_event=self._send_response,
                    )
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
                    job_status.complete_job(
                        job_id,
                        message="索引构建完成",
                        metadata={
                            "chunk_count": result.get("chunk_count", 0),
                            "file_count": result.get("file_count", 0),
                        },
                        send_event=self._send_response,
                    )
                    self._send_response(
                        {
                            "id": "event",
                            "result": {
                                "type": "rag_index_built",
                                "success": True,
                                "chunk_count": result.get("chunk_count", 0),
                                "file_count": result.get("file_count", 0),
                            },
                        }
                    )
            except Exception as e:
                job_status.fail_job(job_id, str(e), send_event=self._send_response)
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
            if time.time() - ts < config.rag_error_cooldown_seconds:
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
        from sidecar.intent_router import classify_intent
        from utils.llm_utils import APIConfigError, check_api_config

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

        history = self._limited_history(params.get("history"))
        profile = self._load_user_profile(workspace)
        context = self._personal_context(profile, history)
        if params.get("selection_lookup"):
            return self._answer_selection_lookup(params, question, use_vector_rag=use_vector_rag)

        forced_intent = params.get("force_intent")
        intent = {"intent": forced_intent, "confidence": "forced", "reason": "前端明确指定"} if forced_intent else classify_intent(question, history=history)
        logger.info(f"[rag/intent] {intent['intent']} ({intent['confidence']}): {intent['reason']}")

        if intent["intent"] in ("chat", "general"):
            return self._answer_without_retrieval(question, context, intent=intent["intent"])
        if intent["intent"] == "web":
            return self._answer_without_retrieval(question, context, intent="web")

        # workspace / unknown -> RAG retrieval
        return self._answer_with_rag(params, question, context, use_vector_rag=use_vector_rag)

    @staticmethod
    def _limited_history(raw_history) -> str:
        if not isinstance(raw_history, list):
            return ""
        lines = []
        for message in raw_history[-6:]:
            if not isinstance(message, dict):
                continue
            role = "用户" if message.get("role") == "user" else "助手"
            content = str(message.get("content") or "").strip()[:1200]
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)[:5000]

    @staticmethod
    def _load_user_profile(workspace: str) -> str:
        profile_path = Path(workspace) / ".ai_memory" / "user_profile.json"
        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        return str(data.get("profile_md") or "").strip()[:4000]

    @staticmethod
    def _personal_context(profile: str, history: str) -> str:
        parts = []
        if profile:
            parts.append(f"用户画像（仅用于理解用户背景，不视为知识库证据）：\n{profile}")
        if history:
            parts.append(f"当前会话最近上下文：\n{history}")
        return "\n\n".join(parts)

    def _answer_selection_lookup(self, params, selection: str, *, use_vector_rag: bool) -> dict:
        """Stream a quick explanation first, then append evidence from the selected route."""
        from sidecar.intent_router import classify_intent
        from utils.llm_utils import APIConfigError, call_llm_raw_stream

        current_file = params.get("current_file") or ""
        context = (params.get("selection_context") or "").strip()[:2000]
        prompt = (
            "你在帮助用户阅读笔记。先给出简洁、明确的快速解释；这不是检索结论，"
            "不要编造来源。\n\n"
            f"选中文本：{selection}\n当前文件：{current_file or '未知'}\n上下文：{context or '未提供'}"
        )
        try:
            quick_answer = call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=self._send_chat_chunk)
        except (APIConfigError, Exception) as e:
            return self._fail_rag(str(e))

        requested_route = params.get("selection_route", "auto")
        if requested_route == "rag":
            route = "workspace"
        elif requested_route == "web":
            route = "web"
        else:
            route_query = f"选中文本：{selection}\n上下文：{context}" if context else selection
            route = classify_intent(route_query, history="").get("intent", "unknown")

        if route in {"workspace", "unknown"}:
            self._send_chat_chunk("\n\n---\n\n### 知识库补充\n\n")
            return self._answer_with_rag(params, selection, "", use_vector_rag=use_vector_rag)
        if route == "web":
            self._send_chat_chunk("\n\n---\n\n### 联网补充\n\n")
            return self._answer_without_retrieval(selection, "", intent="web")
        return self._finish_chat(selection, quick_answer)

    def _send_chat_chunk(self, token: str) -> None:
        self._send_response(
            {
                "id": "event",
                "result": {"type": "rag_chat_chunk", "token": token},
            }
        )

    def _citation_quality(self, citations: list | None) -> dict:
        cites = citations or []
        scored = []
        for cite in cites:
            try:
                scored.append(float(cite.get("score")))
            except (TypeError, ValueError):
                continue
        source_count = len([c for c in cites if c.get("file_path") and c.get("source_type") != "current"])
        top_score = max(scored) if scored else None
        if source_count == 0:
            level = "none"
        elif top_score is None or top_score < 0.22:
            level = "weak"
        elif source_count >= 6:
            level = "broad"
        elif source_count <= 3 and (top_score is None or top_score >= 0.72):
            level = "focused"
        else:
            level = "balanced"
        return {"source_count": source_count, "level": level, "top_score": top_score}

    def _finish_chat(self, question: str, answer: str, citations: list | None = None) -> dict:
        from sidecar.archive_wiki import parse_save_suggestion

        display_answer, suggest_save_note = parse_save_suggestion(answer)
        if not display_answer.strip():
            return self._fail_rag("AI 未生成回复")

        RagHandler._clear_error_reset()

        self._send_response(
            {
                "id": "event",
                "result": {
                    "type": "rag_chat_done",
                    "answer": display_answer,
                    "suggest_save_note": suggest_save_note,
                    "citations": citations or [],
                    "citation_quality": self._citation_quality(citations),
                },
            }
        )
        return {"success": True, "suggest_save_note": suggest_save_note}

    def _answer_without_retrieval(self, question: str, compressed_history: str, *, intent: str = "general") -> dict:
        from prompts import ASSISTANT_PERSONA_PROMPT, RAG_ASSISTANT_NO_CONTEXT_PROMPT, RAG_ASSISTANT_WEB_PROMPT
        from utils.llm_utils import APIConfigError, call_llm_raw_stream

        memory_section = f"对话历史：{compressed_history}\n\n" if compressed_history else ""

        if intent == "web":
            from sidecar.rag.web_search import search_and_fetch

            web_results = []
            try:
                web_results = search_and_fetch(question, max_pages=2)
            except Exception as e:
                logger.warning(f"[rag/web] search failed: {e}")

            web_context_parts = []
            for idx, r in enumerate(web_results, 1):
                title = r.get("title", "")
                url = r.get("url", "")
                content = (r.get("content") or r.get("snippet") or "").strip()[:1200]
                if title or content:
                    web_context_parts.append(f"[{idx}] {title}\n{url}\n{content}")

            web_context = "\n\n".join(web_context_parts) if web_context_parts else "未搜索到有效结果。"
            prompt = RAG_ASSISTANT_WEB_PROMPT.format(
                persona=ASSISTANT_PERSONA_PROMPT,
                memory_section=memory_section,
                web_context=web_context,
                question=question,
            )
        else:
            prompt = RAG_ASSISTANT_NO_CONTEXT_PROMPT.format(
                persona=ASSISTANT_PERSONA_PROMPT,
                memory_section=memory_section,
                question=question,
            )

        try:
            answer = call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=self._send_chat_chunk)
        except APIConfigError as e:
            RagHandler._record_error(f"LLM调用失败: {e}")
            return self._fail_rag(str(e))
        except Exception as e:
            RagHandler._record_error(f"LLM错误: {e}")
            return self._fail_rag(str(e))

        citations = []
        if intent == "web":
            citations = [
                {
                    "index": i,
                    "file_path": "",
                    "file_name": result.get("title", ""),
                    "source_label": result.get("title", ""),
                    "source_type": "web",
                    "url": result.get("url", ""),
                }
                for i, result in enumerate(web_results, 1)
                if result.get("url")
            ]
        return self._finish_chat(question, answer, citations=citations)

    def _answer_with_rag(self, params, question: str, compressed_history: str, *, use_vector_rag: bool) -> dict:
        from prompts import RAG_CHAT_PROMPT
        from utils.llm_utils import APIConfigError, call_llm_raw_stream

        topics = params.get("topics") or None
        tags = params.get("tags") or None
        current_file = params.get("current_file") or ""

        if use_vector_rag:
            from sidecar.rag.retriever import retrieve as search_fn
        else:
            from sidecar.classic_retriever import retrieve as search_fn

        try:
            search_results = search_fn(question, topics=topics, tags=tags)
        except Exception as e:
            RagHandler._record_error(f"检索失败: {e}")
            return self._fail_rag(f"检索失败: {e}")

        context_parts = []
        citations = []
        seen_paths: set[str] = set()

        # The current file is useful background, but it is not evidence unless
        # retrieval independently returns a scored chunk from that file.
        if current_file:
            current_full = self._resolve_path(current_file)
            try:
                if current_full:
                    cf_text = Path(current_full).read_text(encoding="utf-8")
                    _, cf_body = self._parse_frontmatter(cf_text)
                    cf_body = (cf_body or cf_text).strip()[:4000]
                    if cf_body:
                        label = Path(current_file).stem
                        context_parts.append(f"当前打开文件背景（不可作为引用）：{label}\n{cf_body}")
            except Exception:
                pass

        for r in search_results:
            body = (r.get("content") or "").strip()
            if not body:
                continue
            fp = r.get("file_path", "")
            if fp and fp in seen_paths:
                continue
            if fp:
                seen_paths.add(fp)
            label = r.get("source_label") or r.get("file_name") or fp or ""
            idx = len(context_parts) + 1
            context_parts.append(f"[{idx}] {label}\n{body}")
            citations.append(
                {
                    "index": idx,
                    "file_path": fp,
                    "file_name": r.get("file_name") or Path(fp).stem,
                    "source_label": r.get("source_label") or "",
                    "section_title": r.get("section_title") or "",
                    "topic": r.get("topic") or "",
                    "source_type": r.get("source_type") or "vector",
                    "score": r.get("rerank_score", r.get("score")),
                }
            )
        context = "\n\n".join(context_parts)

        prompt = RAG_CHAT_PROMPT.format(
            context=context,
            history=compressed_history if compressed_history else "无历史对话",
            question=question,
        )

        try:
            answer = call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=self._send_chat_chunk)
        except APIConfigError as e:
            RagHandler._record_error(f"LLM调用失败: {e}")
            return self._fail_rag(str(e))
        except Exception as e:
            RagHandler._record_error(f"LLM错误: {e}")
            return self._fail_rag(str(e))

        return self._finish_chat(question, answer, citations=citations)

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

    def _rag_rebuild_index(self, params):
        """Manual index update; incremental when the existing collection is healthy."""
        return self._init_rag_index(params)

    def _rag_index_status(self, params):
        if not config.rag_enabled:
            return {"success": True, "enabled": False, "built": False, "chunk_count": 0, "file_count": 0}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        from sidecar.ingest_pipeline import load_ingest_state
        from sidecar.rag.index import count_indexed_chunks, index_exists, load_manifest, manifest_path

        try:
            exists = index_exists(workspace)
            chunk_count = count_indexed_chunks(workspace)
            manifest = load_manifest(workspace)
            files = manifest.get("files", {})
            expected_chunks = sum(len(entry.get("chunks") or []) for entry in files.values())
            file_count = len(files)
            mtime = None
            if manifest_path(workspace).exists():
                mtime = Path(manifest_path(workspace)).stat().st_mtime

            ingest_state = load_ingest_state()
            is_building = ingest_state.get("status") == "running" and ingest_state.get("stage") in (
                "convert",
                "compile",
                "classify",
                "index",
                "crossref",
            )
            percent = 0.0
            if is_building:
                progress = ingest_state.get("progress")
                if isinstance(progress, (int, float)) and 0 <= progress <= 1:
                    percent = round(progress * 100, 1)
                else:
                    stage_progress = {
                        "convert": 16,
                        "compile": 28,
                        "classify": 45,
                        "index": 65,
                        "crossref": 70,
                    }
                    percent = stage_progress.get(ingest_state.get("stage"), 0)

            return {
                "success": True,
                "enabled": True,
                "built": exists and chunk_count > 0 and chunk_count == expected_chunks,
                "needs_rebuild": not (exists and chunk_count > 0 and chunk_count == expected_chunks),
                "repair_required": expected_chunks > 0 and chunk_count != expected_chunks,
                "chunk_count": chunk_count,
                "expected_chunks": expected_chunks,
                "file_count": file_count,
                "mtime": mtime,
                "is_building": is_building,
                "percent": percent,
                "stage": ingest_state.get("stage") if is_building else None,
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def register_routes(self, router):
        router.register("init_rag_index", self._init_rag_index)
        router.register("rag_rebuild_index", self._rag_rebuild_index)
        router.register("rag_add_chunks", self._rag_add_chunks)
        router.register("rag_remove_chunks", self._rag_remove_chunks)
        router.register("rag_chat", self._rag_chat, async_mode=True)
        router.register("rag_clear_memory", self._rag_clear_memory)
        router.register("rag_index_status", self._rag_index_status)
