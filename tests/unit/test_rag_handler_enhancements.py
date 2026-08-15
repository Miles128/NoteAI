"""单元测试：rag_handler 的 P4/P9 增强（哨兵剥离、主题锚定、模板追问、流式攒批）。"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from sidecar.handlers.rag_handler import RagHandler

from config import config

# ---------------------------------------------------------------------------
# _strip_suggestions_sentinel：SUGGESTIONS_JSON 哨兵剥离
# ---------------------------------------------------------------------------


def test_strip_sentinel_parses_suggestions():
    answer = '这是回答正文。\nSUGGESTIONS_JSON:["再讲讲细节", "有例子吗"]'
    body, suggestions = RagHandler._strip_suggestions_sentinel(answer)
    assert "这是回答正文" in body
    assert "SUGGESTIONS_JSON" not in body
    assert suggestions == ["再讲讲细节", "有例子吗"]


def test_strip_sentinel_empty_array():
    body, suggestions = RagHandler._strip_suggestions_sentinel("正文\nSUGGESTIONS_JSON:[]")
    assert body == "正文"
    assert suggestions == []


def test_strip_sentinel_missing_returns_unchanged():
    body, suggestions = RagHandler._strip_suggestions_sentinel("只有正文")
    assert body == "只有正文"
    assert suggestions == []


def test_strip_sentinel_invalid_json_is_dropped():
    body, suggestions = RagHandler._strip_suggestions_sentinel("正文\nSUGGESTIONS_JSON:[not json]")
    assert body == "正文"
    assert suggestions == []


def test_strip_sentinel_caps_at_three():
    body, suggestions = RagHandler._strip_suggestions_sentinel('正文\nSUGGESTIONS_JSON:["a","b","c","d"]')
    assert body == "正文"
    assert suggestions == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# _session_topic_anchors：会话内主题锚定（仅会话内存活，不持久化）
# ---------------------------------------------------------------------------


def _mk_history(n_pairs: int) -> list:
    history = []
    for i in range(n_pairs):
        history.append({"role": "user", "content": f"第{i}轮：请讲讲机器学习中的梯度下降问题"})
        history.append({"role": "assistant", "content": f"第{i}轮：梯度下降是一种优化算法"})
    return history


def test_anchors_empty_when_history_short():
    assert RagHandler._session_topic_anchors(None) == []
    assert RagHandler._session_topic_anchors([]) == []
    assert RagHandler._session_topic_anchors(_mk_history(3)) == []  # 6 条及以下不触发


def test_anchors_extracts_terms_from_older_turns():
    history = _mk_history(5)  # 10 条 > 6
    with patch("sidecar.handlers.rag_handler._jieba_analyse_available", return_value=True):
        anchors = RagHandler._session_topic_anchors(history)
    assert isinstance(anchors, list)
    assert anchors  # jieba 应能从压缩前文中提取出词
    assert len(anchors) <= 5


def test_anchors_skips_invalid_entries():
    history = ["bad", {"no_role": True}] + _mk_history(4)
    with patch("sidecar.handlers.rag_handler._jieba_analyse_available", return_value=True):
        anchors = RagHandler._session_topic_anchors(history)
    assert isinstance(anchors, list)


def test_anchors_empty_without_jieba():
    with patch("sidecar.handlers.rag_handler._jieba_analyse_available", return_value=False):
        assert RagHandler._session_topic_anchors(_mk_history(5)) == []


def test_answer_with_rag_pipeline_injects_anchors(tmp_path, monkeypatch):
    """集成：前端上送的 12 条 history 经 _answer_with_rag 完整路径，
    锚点词应注入检索 query 并回传 retrieval_debug.anchor_terms（P4 链路打通）。"""
    monkeypatch.setattr(config, "workspace_path", str(tmp_path))
    events: list = []
    handler = RagHandler(
        SimpleNamespace(
            _ctx=SimpleNamespace(config=config, logger=None),
            _send_response=lambda resp: events.append(resp),
        )
    )

    history = []
    for _ in range(6):
        history.append({"role": "user", "content": "请讲讲量子计算中超导量子比特的退相干问题"})
        history.append({"role": "assistant", "content": "超导量子比特的退相干主要来自环境噪声与门操作误差。"})
    assert len(history) == 12

    anchors = RagHandler._session_topic_anchors(history)
    assert anchors  # jieba 应能从早轮历史提取出锚点词

    captured: dict = {}

    def fake_retrieve(query, topics=None, tags=None, current_file=""):
        captured["query"] = query
        return {"results": [], "retrieval_debug": {}}

    import sidecar.rag.claim_context as claim_mod
    import sidecar.rag.object_context as object_mod
    import sidecar.rag.retriever as retriever_mod

    import utils.llm_utils as llm_mod

    monkeypatch.setattr(retriever_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(claim_mod, "retrieve_claim_context", lambda *a, **k: [])
    monkeypatch.setattr(object_mod, "retrieve_object_context", lambda *a, **k: [])
    monkeypatch.setattr(llm_mod, "call_llm_raw_stream", lambda prompt, **k: "回答正文")

    result = handler._answer_with_rag({"history": history}, "继续", "", use_vector_rag=True)

    assert result["success"] is True
    # 检索 query = 原问题 + 锚点词，原问题保持完整在前
    assert captured["query"].startswith("继续 ")
    for term in anchors:
        assert term in captured["query"]
    # 回传给前端面板的 retrieval_debug 携带 anchor_terms
    meta_events = [
        e for e in events if e.get("result", {}).get("type") == "rag_retrieval" and e["result"].get("subtype") == "meta"
    ]
    assert meta_events
    assert meta_events[0]["result"]["data"]["retrieval_debug"]["anchor_terms"] == anchors


# ---------------------------------------------------------------------------
# _template_suggestions：模板化追问兜底（不调 LLM）
# ---------------------------------------------------------------------------


def test_template_suggestions_prefers_topic():
    citations = [
        {"topic": "AI > RAG", "section_title": "原理", "source_label": "a.md"},
        {"topic": "", "section_title": "实践", "source_label": "b.md"},
        {"topic": "", "section_title": "", "source_label": "c.md"},
    ]
    suggestions = RagHandler._template_suggestions(citations)
    assert suggestions == ["「AI > RAG」还有哪些相关笔记？", "展开讲讲「实践」", "《c.md》里还有什么要点？"]


def test_template_suggestions_empty_without_citations():
    assert RagHandler._template_suggestions(None) == []
    assert RagHandler._template_suggestions([]) == []


def test_template_suggestions_dedup_and_cap():
    citations = [{"topic": "AI > RAG"} for _ in range(10)]
    suggestions = RagHandler._template_suggestions(citations)
    assert suggestions == ["「AI > RAG」还有哪些相关笔记？"]


# ---------------------------------------------------------------------------
# RagChatChunkBatcher：流式 token 攒批


def _batcher_capture():
    """返回 (batcher 发送捕获器, sent)。捕获器模拟真实 _send_response（json.dumps 后写 stdout）。"""
    import json

    sent: list[str] = []

    def send(payload):
        sent.append(json.dumps(payload, ensure_ascii=False))

    return send, sent


def test_batcher_flushes_batched_payload():
    from sidecar.handlers.rag_handler import RagChatChunkBatcher

    send, sent = _batcher_capture()
    batcher = RagChatChunkBatcher(send, flush_interval=0.01, max_chars=50)

    batcher.append("hello ")
    batcher.append("world")
    batcher.flush()

    assert len(sent) == 1
    payload = json.loads(sent[0])
    assert payload["id"] == "event"
    assert payload["result"] == {"type": "rag_chat_chunk", "token": "hello world"}


def test_batcher_flushes_on_size_threshold():
    from sidecar.handlers.rag_handler import RagChatChunkBatcher

    send, sent = _batcher_capture()
    batcher = RagChatChunkBatcher(send, flush_interval=60, max_chars=10)

    for token in ["a", "b", "c", "d", "e", "f", "g", "h"]:
        batcher.append(token)
    batcher.flush()

    # 满 10 字符阈值触发一次 flush，其余空 buffer 不再发送
    assert len(sent) == 1


def test_batcher_ignores_empty_tokens_and_after_close():
    from sidecar.handlers.rag_handler import RagChatChunkBatcher

    send, sent = _batcher_capture()
    batcher = RagChatChunkBatcher(send, flush_interval=60, max_chars=200)
    batcher.append("")
    batcher.append("x")
    batcher.flush()
    assert len(sent) == 1
    assert json.loads(sent[0])["result"]["token"] == "x"

    batcher.append("after-close")
    batcher.flush()
    assert len(sent) == 1


def test_batcher_timer_flushes_without_flush_call():
    import time

    from sidecar.handlers.rag_handler import RagChatChunkBatcher

    send, sent = _batcher_capture()
    batcher = RagChatChunkBatcher(send, flush_interval=0.02, max_chars=1000)
    batcher.append("streaming ")
    batcher.append("token")
    time.sleep(0.08)
    batcher.flush()
    assert len(sent) >= 1
    assert json.loads(sent[-1])["result"]["token"] == "streaming token"


# ---------------------------------------------------------------------------
# 按 session 的对话门禁：同会话串行 / 不同会话并行
# ---------------------------------------------------------------------------


def test_chat_gate_serializes_same_session():
    from sidecar.handlers.rag_handler import RagHandler

    handler = RagHandler.__new__(RagHandler)
    gate = handler._acquire_chat_gate("session-a")
    assert gate is not None
    # 同 session 第二个请求被拒绝
    assert handler._acquire_chat_gate("session-a") is None
    handler._release_chat_gate(gate, "session-a")
    # 释放后可再次进入
    gate2 = handler._acquire_chat_gate("session-a")
    assert gate2 is not None
    handler._release_chat_gate(gate2, "session-a")


def test_chat_gate_allows_parallel_sessions():
    from sidecar.handlers.rag_handler import RagHandler

    handler = RagHandler.__new__(RagHandler)
    gate_a = handler._acquire_chat_gate("session-a")
    gate_b = handler._acquire_chat_gate("session-b")
    assert gate_a is not None and gate_b is not None
    handler._release_chat_gate(gate_a, "session-a")
    handler._release_chat_gate(gate_b, "session-b")


def test_chat_gate_global_fallback_serializes():
    from sidecar.handlers.rag_handler import RagHandler

    handler = RagHandler.__new__(RagHandler)
    gate = handler._acquire_chat_gate("_global")
    assert gate is not None
    assert handler._acquire_chat_gate("_global") is None
    handler._release_chat_gate(gate, "_global")


def test_chat_gate_cleans_up_idle_entries():
    from sidecar.handlers.rag_handler import RagHandler

    handler = RagHandler.__new__(RagHandler)
    gate = handler._acquire_chat_gate("session-tmp")
    handler._release_chat_gate(gate, "session-tmp")
    # 空闲锁已从字典移除，不泄漏
    with RagHandler._session_gates_guard:
        assert "session-tmp" not in RagHandler._session_gates
    with RagHandler._session_gates_guard:
        RagHandler._session_gates.clear()
