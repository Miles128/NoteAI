"""单元测试：python/sidecar/intent_router.py 意图路由。

覆盖 _parse_intent_json 的各解析分支，以及 classify_intent 在
mock LLM 下的分类分支与关键词兜底逻辑。
"""

import pytest
from sidecar.intent_router import _INTENT_ORDER, _parse_intent_json, classify_intent

# ---------------------------------------------------------------------------
# _parse_intent_json：解析分支
# ---------------------------------------------------------------------------


def test_parse_valid_json_returns_dict():
    result = _parse_intent_json('{"intent": "workspace", "confidence": "high", "reason": "local"}')
    assert result == {"intent": "workspace", "confidence": "high", "reason": "local"}


def test_parse_strips_surrounding_whitespace():
    result = _parse_intent_json('  \n {"intent": "web"} \n ')
    assert result == {"intent": "web"}


def test_parse_json_code_fence_with_lang():
    raw = '```json\n{"intent": "general", "confidence": "medium"}\n```'
    assert _parse_intent_json(raw) == {"intent": "general", "confidence": "medium"}


def test_parse_json_code_fence_without_lang():
    raw = '```\n{"intent": "chat"}\n```'
    assert _parse_intent_json(raw) == {"intent": "chat"}


def test_parse_json_embedded_in_prose_via_regex_fallback():
    raw = '好的，分类结果如下：{"intent": "workspace", "reason": "笔记查询"} 希望有帮助'
    result = _parse_intent_json(raw)
    assert result == {"intent": "workspace", "reason": "笔记查询"}


def test_parse_invalid_json_returns_none():
    assert _parse_intent_json("这不是 JSON") is None


def test_parse_invalid_json_inside_fence_returns_none():
    assert _parse_intent_json("```json\n{intent: bad}\n```") is None


def test_parse_non_dict_json_returns_none():
    assert _parse_intent_json('["intent", "workspace"]') is None
    assert _parse_intent_json('"workspace"') is None


def test_parse_empty_and_none_returns_none():
    assert _parse_intent_json("") is None
    assert _parse_intent_json("   ") is None
    assert _parse_intent_json(None) is None  # type: ignore[arg-type]


def test_parse_fence_with_prose_inside_falls_back_to_regex():
    # fence 剥离后仍非合法 JSON，但内含合法对象 → 正则兜底
    raw = '```\n前缀 {"intent": "web"} 后缀\n```'
    assert _parse_intent_json(raw) == {"intent": "web"}


# ---------------------------------------------------------------------------
# classify_intent：启发式与关键词兜底（无需 LLM）
# ---------------------------------------------------------------------------


def test_empty_question_returns_unknown():
    result = classify_intent("")
    assert result == {"intent": "unknown", "confidence": "high", "reason": "empty question"}

    result_ws = classify_intent("   \n")
    assert result_ws["intent"] == "unknown"
    assert result_ws["reason"] == "empty question"


@pytest.mark.parametrize(
    "question",
    ["你好", "你好，帮我看下东西", "hello there", "hi", "谢谢您", "在吗"],
)
def test_greeting_shortcut_returns_chat(question: str):
    result = classify_intent(question)
    assert result["intent"] == "chat"
    assert result["confidence"] == "high"
    assert result["reason"] == "greeting/thanks heuristic"


@pytest.mark.parametrize(
    "question,indicator",
    [
        ("帮我找找我的笔记里关于RAG的内容", "我的笔记"),
        ("工作区里有哪些文件", "工作区"),
        ("这篇文章讲了什么", "这篇文章"),
        ("打开 notes/guide.md", "notes/"),
    ],
)
def test_workspace_keyword_fallback(question: str, indicator: str):
    assert indicator in question.lower() or indicator in question
    result = classify_intent(question)
    assert result == {"intent": "workspace", "confidence": "high", "reason": "workspace keyword detected"}


def test_web_keyword_fallback():
    result = classify_intent("搜一下最近的AI新闻")
    assert result == {"intent": "web", "confidence": "medium", "reason": "web keyword detected"}


# ---------------------------------------------------------------------------
# classify_intent：mock LLM 分支
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_env(monkeypatch):
    """放行 API 配置检查，并提供替换 call_llm_raw 的辅助函数。"""
    monkeypatch.setattr("utils.llm_utils.check_api_config", lambda: (True, ""))

    def install(fake_fn):
        monkeypatch.setattr("utils.llm_utils.call_llm_raw", fake_fn)

    return install


def test_api_not_configured_falls_back_to_workspace(monkeypatch):
    monkeypatch.setattr("utils.llm_utils.check_api_config", lambda: (False, "no key"))
    result = classify_intent("解释一下量子纠缠")
    assert result["intent"] == "workspace"
    assert result["confidence"] == "low"
    assert "API unavailable" in result["reason"]


def test_llm_exception_falls_back_to_workspace(llm_env):
    def boom(prompt, temperature=None, max_tokens=None):
        raise RuntimeError("upstream timeout")

    llm_env(boom)
    result = classify_intent("解释一下量子纠缠")
    assert result["intent"] == "workspace"
    assert result["confidence"] == "low"
    assert "classification error" in result["reason"]


def test_unparseable_llm_output_falls_back_to_workspace(llm_env):
    llm_env(lambda prompt, **kwargs: "抱歉，我无法分类")
    result = classify_intent("解释一下量子纠缠")
    assert result["intent"] == "workspace"
    assert result["confidence"] == "low"
    assert "unparseable model output" in result["reason"]


@pytest.mark.parametrize("intent", list(_INTENT_ORDER))
def test_llm_returns_each_known_intent(llm_env, intent: str):
    llm_env(lambda prompt, **kwargs: f'{{"intent": "{intent}", "confidence": "high", "reason": "r"}}')
    result = classify_intent("解释一下量子纠缠")
    assert result["intent"] == intent
    assert result["confidence"] == "high"
    assert result["reason"] == "r"


def test_llm_intent_case_and_whitespace_normalized(llm_env):
    llm_env(lambda prompt, **kwargs: '{"intent": "  WEB  ", "confidence": " HIGH ", "reason": "  news  "}')
    result = classify_intent("解释一下量子纠缠")
    assert result["intent"] == "web"
    assert result["confidence"] == "high"
    assert result["reason"] == "news"


def test_llm_unknown_intent_maps_to_unknown(llm_env):
    llm_env(lambda prompt, **kwargs: '{"intent": "bogus"}')
    result = classify_intent("解释一下量子纠缠")
    assert result["intent"] == "unknown"
    # 缺省 confidence / reason 的默认值
    assert result["confidence"] == "medium"
    assert result["reason"] == "classified by model"


def test_llm_missing_fields_use_defaults(llm_env):
    # 非空 dict 但缺少 intent/reason 字段 → intent 归为 unknown，其余取默认值
    llm_env(lambda prompt, **kwargs: '{"confidence": "high"}')
    result = classify_intent("解释一下量子纠缠")
    assert result == {"intent": "unknown", "confidence": "high", "reason": "classified by model"}


def test_llm_empty_dict_output_is_treated_as_unparseable(llm_env):
    # 实际行为：空 dict 为假值，`if not parsed` 命中 unparseable 兜底分支
    llm_env(lambda prompt, **kwargs: "{}")
    result = classify_intent("解释一下量子纠缠")
    assert result["intent"] == "workspace"
    assert result["confidence"] == "low"
    assert "unparseable model output" in result["reason"]


def test_llm_output_in_code_fence_is_parsed(llm_env):
    llm_env(lambda prompt, **kwargs: '```json\n{"intent": "workspace", "reason": "笔记"}\n```')
    result = classify_intent("解释一下量子纠缠")
    assert result["intent"] == "workspace"
    assert result["confidence"] == "medium"
    assert result["reason"] == "笔记"


def test_keyword_rules_take_precedence_over_llm(llm_env):
    # 即便 LLM 返回 web，工作区关键词也应先命中本地兜底
    calls = []

    def fake(prompt, temperature=None, max_tokens=None):
        calls.append(prompt)
        return '{"intent": "web"}'

    llm_env(fake)
    result = classify_intent("我的笔记里有什么")
    assert result["intent"] == "workspace"
    assert calls == []  # 关键词命中后不应触发 LLM 调用
