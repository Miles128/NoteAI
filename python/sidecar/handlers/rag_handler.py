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


def _jieba_analyse_available():
    """Check if jieba.analyse is importable (lazy, cached)."""
    try:
        import jieba.analyse  # noqa: F401

        return True
    except ImportError:
        return False


class RagHandler(BaseHandler):
    _rag_chat_lock = threading.Lock()
    _rag_build_lock = threading.Lock()

    _SUGGESTIONS_SENTINEL_RE = re.compile(r"SUGGESTIONS_JSON:\s*(\[[^\]]*\])")

    @staticmethod
    def _strip_suggestions_sentinel(answer: str) -> tuple[str, list[str]]:
        """Split the trailing SUGGESTIONS_JSON sentinel; return (body, suggestions)."""
        raw = answer or ""
        m = RagHandler._SUGGESTIONS_SENTINEL_RE.search(raw)
        if not m:
            return raw, []
        body = raw[: m.start()].rstrip()
        try:
            data = json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError, ValueError):
            return body, []
        if not isinstance(data, list):
            return body, []
        suggestions = [str(s).strip() for s in data if str(s).strip()][:3]
        return body, suggestions

    @staticmethod
    def _session_topic_anchors(history) -> list[str]:
        """Session-only topic anchoring: extract anchor terms from early turns.

        When the session history exceeds 6 messages, the messages before the
        last 6 are compressed via _extractive_compress and mined for
        high-value terms (jieba TF-IDF) used as extra retrieval keywords.
        Lives only in-session: never persisted, no automatic extraction
        pipeline (PRD §3/§12.6).
        """
        if not isinstance(history, list) or len(history) <= 6:
            return []
        older = [m for m in history[:-6] if isinstance(m, dict)]
        if not older or not _jieba_analyse_available():
            return []
        try:
            text = RagHandler._extractive_compress(older)
            if not text.strip():
                text = " ".join(str(m.get("content") or "")[:300] for m in older if m.get("role") == "user")
            if not text.strip():
                return []
            import jieba.analyse

            return list(jieba.analyse.extract_tags(text, topK=5, withWeight=False))
        except Exception as e:
            logger.warning(f"[rag] topic anchoring failed: {e}")
            return []

    @staticmethod
    def _template_suggestions(citations: list | None) -> list[str]:
        """Fallback follow-up suggestions built from citation metadata (no LLM)."""
        suggestions: list[str] = []
        seen: set[str] = set()
        for c in citations or []:
            if not isinstance(c, dict):
                continue
            topic = str(c.get("topic") or "").strip()
            section = str(c.get("section_title") or "").strip()
            label = str(c.get("source_label") or c.get("file_name") or "").strip()
            if topic and topic not in seen:
                suggestions.append(f"「{topic}」还有哪些相关笔记？")
                seen.add(topic)
            elif section and section not in seen:
                suggestions.append(f"展开讲讲「{section}」")
                seen.add(section)
            elif label and label not in seen:
                suggestions.append(f"《{label}》里还有什么要点？")
                seen.add(label)
            if len(suggestions) >= 3:
                break
        return suggestions[:3]

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

    def _do_rag_chat_inner(self, params, *, use_vector_rag: bool = True):
        from utils.llm_utils import APIConfigError, check_api_config

        question = params.get("question", "").strip()
        if not question:
            return {"success": False, "message": "问题不能为空"}

        workspace, err = self._require_workspace()
        if err:
            return err

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

        # Default every normal conversation to the workspace so a greeting or
        # broadly phrased question cannot silently bypass the evidence path.
        # Web remains available only through an explicit UI override.
        if params.get("force_intent") == "web":
            return self._answer_without_retrieval(question, context, intent="web")
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
            route = classify_intent(route_query, history=params.get("history")).get("intent", "unknown")

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
        source_count = len([c for c in cites if c.get("file_path")])
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

        display_answer, suggestions = RagHandler._strip_suggestions_sentinel(answer)
        if not suggestions and citations:
            # Model omitted the sentinel: fall back to template suggestions.
            suggestions = RagHandler._template_suggestions(citations)
        display_answer, suggest_save_note = parse_save_suggestion(display_answer)
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
                    "suggestions": suggestions,
                    "citations": citations or [],
                    "citation_quality": self._citation_quality(citations),
                },
            }
        )
        return {"success": True, "suggest_save_note": suggest_save_note, "suggestions": suggestions}

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

    def _answer_with_rag(
        self, params, question: str, compressed_history: str, *, use_vector_rag: bool, intent: str = "workspace"
    ) -> dict:
        from prompts import RAG_CHAT_PROMPT
        from utils.llm_utils import APIConfigError, call_llm_raw_stream

        topics = params.get("topics") or None
        tags = params.get("tags") or None
        current_file = params.get("current_file") or ""

        retrieval_debug: dict | None = None
        hyde_enabled_flag = False
        hyde_query: str | None = None
        try:
            if use_vector_rag:
                from sidecar.rag.retriever import retrieve as vector_retrieve

                # Session-only topic anchoring: append anchor terms from early
                # turns as extra retrieval keywords (original query kept intact).
                anchors = RagHandler._session_topic_anchors(params.get("history"))
                retrieval_query = f"{question} {' '.join(anchors)}" if anchors else question
                retrieval = vector_retrieve(
                    retrieval_query,
                    topics=topics,
                    tags=tags,
                    current_file=current_file,
                )
                search_results = retrieval.get("results") or []
                retrieval_debug = dict(retrieval.get("retrieval_debug") or {})
                if anchors:
                    retrieval_debug["anchor_terms"] = anchors
                hyde_enabled_flag = bool(retrieval_debug.get("hyde_enabled"))
                hyde_query = retrieval_debug.get("hyde_query")
            else:
                from sidecar.classic_retriever import retrieve as classic_retrieve

                search_results = classic_retrieve(question, topics=topics, tags=tags)
        except Exception as e:
            RagHandler._record_error(f"检索失败: {e}")
            return self._fail_rag(f"检索失败: {e}")

        context_parts: list[str] = []
        citations: list[dict] = []
        seen_paths: set[str] = set()

        # Claim-layer injection (P0): verified conclusions + conflict disclosure.
        # Best-effort — a missing or broken semantic DB yields no claim items and
        # the normal chunk-only path is unchanged.
        claim_items: list[dict] = []
        try:
            from sidecar.rag.claim_context import retrieve_claim_context

            claim_items = retrieve_claim_context(config.workspace_path, question, topics=topics, tags=tags)
        except Exception as e:
            logger.warning(f"[rag/claim_context] injection failed: {e}")
        for r in claim_items:
            body = (r.get("content") or "").strip()
            if not body:
                continue
            idx = len(context_parts) + 1
            label = r.get("source_label") or "知识库结论"
            context_parts.append(f"[{idx}] {label}\n{body}")
            fp = r.get("file_path", "")
            citations.append(
                {
                    "index": idx,
                    "file_path": fp,
                    "file_name": r.get("file_name") or (Path(fp).stem if fp else ""),
                    "source_label": label,
                    "section_title": "",
                    "topic": r.get("topic") or "",
                    "source_type": "claim",
                    "score": r.get("score", 0),
                }
            )

        # Object-layer injection: extracted entities/concepts (with descriptions)
        # ground the answer in the knowledge base's structured objects.
        # Best-effort — a missing or broken semantic DB yields no object items.
        object_items: list[dict] = []
        try:
            from sidecar.rag.object_context import retrieve_object_context

            object_items = retrieve_object_context(config.workspace_path, question, topics=topics, tags=tags)
        except Exception as e:
            logger.warning(f"[rag/object_context] injection failed: {e}")
        for r in object_items:
            body = (r.get("content") or "").strip()
            if not body:
                continue
            idx = len(context_parts) + 1
            label = r.get("source_label") or "知识库对象"
            context_parts.append(f"[{idx}] {label}\n{body}")
            citations.append(
                {
                    "index": idx,
                    "file_path": "",
                    "file_name": "",
                    "source_label": label,
                    "section_title": "",
                    "topic": r.get("topic") or "",
                    "source_type": "object",
                    "score": r.get("score", 0),
                }
            )

        for r in search_results:
            # Surveys and graph neighbors are helpful retrieval expansion, but
            # are not direct evidence for a conversational answer.
            if r.get("source_type") in {"survey", "backlink", "topic_tree"}:
                continue
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

        # P9: emit retrieval transparency meta after retrieval, before the
        # answer stream starts.
        meta_data = self._build_retrieval_meta(intent, hyde_enabled_flag, hyde_query, retrieval_debug, search_results)
        self._send_response(
            {
                "id": "event",
                "result": {
                    "type": "rag_retrieval",
                    "subtype": "meta",
                    "session_id": str(params.get("session_id") or ""),
                    "data": meta_data,
                },
            }
        )

        if not context.strip():
            # No evidence at all: explicitly declare the knowledge base has no
            # directly relevant material instead of letting the model improvise
            # with an empty context (which encourages fabricated citations).
            from prompts import ASSISTANT_PERSONA_PROMPT, RAG_ASSISTANT_NO_EVIDENCE_PROMPT

            memory_section = f"对话历史：{compressed_history}\n\n" if compressed_history else ""
            prompt = RAG_ASSISTANT_NO_EVIDENCE_PROMPT.format(
                persona=ASSISTANT_PERSONA_PROMPT,
                memory_section=memory_section,
                question=question,
            )
        else:
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

        return self._finish_chat(question, answer, citations=self._cited_sources(answer, citations))

    @staticmethod
    def _build_retrieval_meta(
        intent: str, hyde_enabled_flag: bool, hyde_query: str | None, retrieval_debug: dict | None, search_results: list
    ) -> dict:
        top_sources = []
        for r in search_results[:5]:
            if not isinstance(r, dict):
                continue
            top_sources.append(
                {
                    "path": r.get("file_path") or "",
                    "section_title": r.get("section_title") or "",
                    "score": r.get("score"),
                    "rerank_score": r.get("rerank_score"),
                }
            )
        return {
            "intent": intent,
            "hyde_enabled": bool(hyde_enabled_flag),
            "hyde_query": (str(hyde_query)[:200] if hyde_query else None),
            "retrieval_debug": retrieval_debug or {},
            "top_sources": top_sources,
        }

    @staticmethod
    def _cited_sources(answer: str, citations: list[dict]) -> list[dict]:
        """Return only valid source IDs the model actually used in its answer."""
        by_index = {str(c.get("index")): c for c in citations if c.get("index") is not None}
        used = []
        seen: set[str] = set()
        for match in re.finditer(r"\[(\d+)\]", answer or ""):
            index = match.group(1)
            if index in by_index and index not in seen:
                used.append(by_index[index])
                seen.add(index)
        return used

    @staticmethod
    def _extractive_compress(older_history):
        if not older_history:
            return ""
        if isinstance(older_history, str):
            return older_history[:800]

        parts = []
        for h in older_history:
            if not isinstance(h, dict):
                continue
            role = "用户" if h.get("role") == "user" else "助手"
            text = str(h.get("content") or "")
            if not text:
                continue
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

            if not _jieba_analyse_available():
                parts.append(f"{role}: {first}…")
                continue

            import jieba.analyse

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

        workspace, err = self._require_workspace()
        if err:
            return err

        from sidecar.ingest_pipeline import load_ingest_state
        from sidecar.rag.index import count_indexed_chunks, index_exists, load_manifest, manifest_path

        try:
            exists = index_exists(workspace)
            chunk_count = count_indexed_chunks(workspace, allow_metadata_fallback=False)
            manifest = load_manifest(workspace)
            files = manifest.get("files", {})
            expected_chunks = sum(len(entry.get("chunks") or []) for entry in files.values())
            file_count = len(files)
            if chunk_count < 0:
                return {
                    "success": True,
                    "enabled": True,
                    "built": False,
                    "busy": True,
                    "needs_rebuild": False,
                    "chunk_count": 0,
                    "expected_chunks": expected_chunks,
                    "file_count": file_count,
                    "is_building": True,
                }
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
                    stage = ingest_state.get("stage")
                    percent = stage_progress.get(stage, 0) if isinstance(stage, str) else 0

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
        router.register("rag_rebuild_index", self._rag_rebuild_index)
        router.register("rag_chat", self._rag_chat)
        router.register("rag_index_status", self._rag_index_status)
