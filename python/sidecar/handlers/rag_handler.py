import contextlib
import json
import re
import threading
from pathlib import Path

from config import config
from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from sidecar import job_status
from sidecar.handlers.base import BaseHandler
from sidecar.rag.chat_answer import answer_with_rag, answer_without_retrieval
from sidecar.rag.chat_stream import RagChatChunkBatcher
from sidecar.rag.chat_stream import SessionGate as _SessionGate
from sidecar.rag.chat_support import (
    _build_retrieval_meta,
    _citation_quality,
    _cited_sources,
    _extractive_compress,
    _limited_history,
    _load_user_profile,
    _personal_context,
    _session_topic_anchors,
    _strip_suggestions_sentinel,
    _template_suggestions,
)


class RagHandler(BaseHandler):
    _session_gates: dict[str, _SessionGate] = {}
    _session_gates_guard = threading.Lock()
    _rag_build_lock = threading.Lock()

    _strip_suggestions_sentinel = staticmethod(_strip_suggestions_sentinel)
    _session_topic_anchors = staticmethod(_session_topic_anchors)
    _template_suggestions = staticmethod(_template_suggestions)
    _limited_history = staticmethod(_limited_history)
    _load_user_profile = staticmethod(_load_user_profile)
    _personal_context = staticmethod(_personal_context)
    _citation_quality = staticmethod(_citation_quality)
    _build_retrieval_meta = staticmethod(_build_retrieval_meta)
    _cited_sources = staticmethod(_cited_sources)
    _extractive_compress = staticmethod(_extractive_compress)

    _SUGGESTIONS_SENTINEL_RE = re.compile(r"SUGGESTIONS_JSON:\s*(\[[^\]]*\])")

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

        session_id = str(params.get("session_id") or "") or "_global"
        gate = self._acquire_chat_gate(session_id)
        if gate is None:
            return {"success": False, "message": "该对话正在进行中，请稍候"}

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
                self._release_chat_gate(gate, session_id)

        threading.Thread(target=_worker, daemon=True).start()
        return {"success": True, "started": True}

    def _acquire_chat_gate(self, session_id: str):
        with RagHandler._session_gates_guard:
            gate = RagHandler._session_gates.setdefault(session_id, _SessionGate())
            gate.users += 1
        if gate.lock.acquire(blocking=False):
            return gate
        with RagHandler._session_gates_guard:
            gate.users -= 1
            if gate.users <= 0:
                RagHandler._session_gates.pop(session_id, None)
        return None

    def _release_chat_gate(self, gate: _SessionGate, session_id: str) -> None:
        gate.lock.release()
        with RagHandler._session_gates_guard:
            gate.users -= 1
            if gate.users <= 0:
                RagHandler._session_gates.pop(session_id, None)

    def _do_rag_chat_inner(self, params, *, use_vector_rag: bool = True):
        from sidecar.rag.model_preload import ModelWarmupManager

        # 兜底触发模型预热：若启动延迟尚未开始（或用户立即提问），确保加载启动
        ModelWarmupManager.ensure_preload()

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

    def _answer_selection_lookup(self, params, selection: str, *, use_vector_rag: bool) -> dict:
        """Stream a quick explanation first, then append evidence from the selected route."""
        from utils.llm_utils import APIConfigError, call_llm_raw_stream

        current_file = params.get("current_file") or ""
        context = (params.get("selection_context") or "").strip()[:2000]
        prompt = (
            "你在帮助用户阅读笔记。先给出简洁、明确的快速解释；这不是检索结论，"
            "不要编造来源。\n\n"
            f"选中文本：{selection}\n当前文件：{current_file or '未知'}\n上下文：{context or '未提供'}"
        )
        try:
            batcher = RagChatChunkBatcher(self._send_response)
            try:
                call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=batcher.append)
            finally:
                batcher.flush()
        except (APIConfigError, Exception) as e:
            return self._fail_rag(str(e))

        # 划词路由：仅尊重显式 UI 覆盖；auto 与主对话一致默认走知识库。
        requested_route = params.get("selection_route", "auto")
        if requested_route == "web":
            self._send_chat_chunk("\n\n---\n\n### 联网补充\n\n")
            return self._answer_without_retrieval(selection, "", intent="web")
        self._send_chat_chunk("\n\n---\n\n### 知识库补充\n\n")
        return self._answer_with_rag(params, selection, "", use_vector_rag=use_vector_rag)

    def _send_chat_chunk(self, token: str) -> None:
        self._send_response(
            {
                "id": "event",
                "result": {"type": "rag_chat_chunk", "token": token},
            }
        )

    def _finish_chat(self, question: str, answer: str, citations: list | None = None) -> dict:
        display_answer, suggestions = RagHandler._strip_suggestions_sentinel(answer)
        if not suggestions and citations:
            # Model omitted the sentinel: fall back to template suggestions.
            suggestions = RagHandler._template_suggestions(citations)
        if not display_answer.strip():
            return self._fail_rag("AI 未生成回复")

        RagHandler._clear_error_reset()

        self._send_response(
            {
                "id": "event",
                "result": {
                    "type": "rag_chat_done",
                    "answer": display_answer,
                    "suggestions": suggestions,
                    "citations": citations or [],
                    "citation_quality": self._citation_quality(citations),
                },
            }
        )
        return {"success": True, "suggestions": suggestions}

    def _answer_without_retrieval(self, question: str, compressed_history: str, *, intent: str = "general") -> dict:
        return answer_without_retrieval(self, question, compressed_history, intent=intent)

    def _answer_with_rag(
        self, params, question: str, compressed_history: str, *, use_vector_rag: bool, intent: str = "workspace"
    ) -> dict:
        return answer_with_rag(self, params, question, compressed_history, use_vector_rag=use_vector_rag, intent=intent)

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
