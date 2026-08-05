"""单元测试：utils/llm_utils.py 的韧性逻辑。

覆盖 _retry_with_backoff（重试次数/退避/可重试性）、_is_retryable_error
判定分支，以及 _run_llm_with_timeout / _run_stream_with_timeout 的
超时与信号量路径（全部使用 mock，不产生真实网络调用）。
"""

from concurrent.futures import TimeoutError as FutureTimeout

import pytest

from utils.llm_utils import (
    _is_retryable_error,
    _retry_with_backoff,
    _run_llm_with_timeout,
    _run_stream_with_timeout,
)

# ---------------------------------------------------------------------------
# _is_retryable_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("Error code: 429 - rate limit exceeded"),
        Exception("Request timed out after 60s"),
        RuntimeError("503 Service Unavailable"),
        Exception("connection reset by peer"),
        Exception("SSL: CERTIFICATE_VERIFY_FAILED"),
        TimeoutError("invoke hang"),  # 类型名含 timeout
        ConnectionError(),  # 消息为空，靠类型名 connection 命中
    ],
)
def test_is_retryable_error_true_branches(exc: Exception):
    assert _is_retryable_error(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("Invalid API key provided"),
        KeyError("model not found"),
        RuntimeError("context_length_exceeded: prompt too long"),
        TypeError("unsupported operand"),
    ],
)
def test_is_retryable_error_false_branches(exc: Exception):
    assert _is_retryable_error(exc) is False


# ---------------------------------------------------------------------------
# _retry_with_backoff
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_sleep(monkeypatch):
    """替换 time.sleep，记录退避时长而不真实等待。"""
    sleeps: list[float] = []
    monkeypatch.setattr("utils.llm_utils.time.sleep", lambda s: sleeps.append(s))
    return sleeps


def test_retry_succeeds_first_attempt_without_sleep(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert _retry_with_backoff(fn) == "ok"
    assert calls == [1]
    assert mock_sleep == []


def test_retry_recovers_after_retryable_failures(mock_sleep):
    outcomes = [RuntimeError("connection reset"), RuntimeError("timed out"), "ok"]

    def fn():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    result = _retry_with_backoff(fn, max_retries=3, base_delay=2.0)
    assert result == "ok"
    assert len(outcomes) == 0  # 共调用 3 次
    # 指数退避：2.0 * 2^0, 2.0 * 2^1
    assert mock_sleep == [2.0, 4.0]


def test_retry_exhausts_attempts_and_raises_last_error(mock_sleep):
    last_error = RuntimeError("503 overloaded")

    def fn():
        raise last_error

    with pytest.raises(RuntimeError, match="503 overloaded"):
        _retry_with_backoff(fn, max_retries=2, base_delay=2.0)
    assert mock_sleep == [2.0, 4.0]  # 3 次尝试，2 次退避

    # 失败路径不得泄漏信号量
    from utils.llm_utils import _LLM_SEMAPHORE

    assert _LLM_SEMAPHORE.acquire(timeout=0.5) is True
    _LLM_SEMAPHORE.release()


def test_retry_stops_immediately_on_non_retryable_error(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("Invalid API key")

    with pytest.raises(ValueError, match="Invalid API key"):
        _retry_with_backoff(fn, max_retries=3)
    assert calls == [1]
    assert mock_sleep == []


def test_retry_respects_max_delay_cap(mock_sleep):
    def fn():
        raise RuntimeError("rate limit")

    with pytest.raises(RuntimeError):
        _retry_with_backoff(fn, max_retries=3, base_delay=10.0, max_delay=15.0)
    # 10 → 15（封顶）→ 15
    assert mock_sleep == [10.0, 15.0, 15.0]


def test_retry_zero_retries_single_attempt(mock_sleep):
    calls = []

    def fn():
        calls.append(1)
        raise RuntimeError("timeout")

    with pytest.raises(RuntimeError):
        _retry_with_backoff(fn, max_retries=0)
    assert calls == [1]
    assert mock_sleep == []


# ---------------------------------------------------------------------------
# _run_llm_with_timeout
# ---------------------------------------------------------------------------


class _FakeFuture:
    def __init__(self, value=None, error=None):
        self._value = value
        self._error = error
        self.cancel_called = False
        self.result_timeout = None

    def result(self, timeout=None):
        self.result_timeout = timeout
        if self._error is not None:
            raise self._error
        return self._value

    def cancel(self):
        self.cancel_called = True


class _FakeExecutor:
    def __init__(self, future):
        self._future = future

    def submit(self, fn):
        return self._future


def test_run_llm_with_timeout_returns_value(monkeypatch):
    future = _FakeFuture(value="result-text")
    monkeypatch.setattr("utils.llm_utils._get_executor", lambda: _FakeExecutor(future))

    assert _run_llm_with_timeout(lambda: "ignored") == "result-text"
    assert future.result_timeout == 90


def test_run_llm_with_timeout_raises_runtime_error_on_timeout(monkeypatch):
    future = _FakeFuture(error=FutureTimeout())
    monkeypatch.setattr("utils.llm_utils._get_executor", lambda: _FakeExecutor(future))

    with pytest.raises(RuntimeError, match="LLM 调用超时"):
        _run_llm_with_timeout(lambda: None)
    assert future.cancel_called is True


# ---------------------------------------------------------------------------
# _run_stream_with_timeout
# ---------------------------------------------------------------------------


class _Chunk:
    def __init__(self, content: str):
        self.content = content


def test_run_stream_concatenates_chunks_and_invokes_callback():
    received: list[str] = []

    def stream_fn():
        return iter([_Chunk("hello "), _Chunk("world  ")])

    text = _run_stream_with_timeout(stream_fn, chunk_callback=received.append)
    assert text == "hello world"  # 结果会被 strip
    assert received == ["hello ", "world  "]


def test_run_stream_supports_plain_string_chunks_without_callback():
    text = _run_stream_with_timeout(lambda: iter(["abc", "def"]))
    assert text == "abcdef"


def test_run_stream_reraises_producer_error():
    def stream_fn():
        raise RuntimeError("boom upstream")
        yield  # 使函数成为生成器（不可达，仅为满足协议）

    with pytest.raises(RuntimeError, match="boom upstream"):
        _run_stream_with_timeout(stream_fn)


def test_run_stream_reraises_error_raised_mid_iteration():
    def stream_fn():
        yield _Chunk("partial")
        raise ConnectionError("reset mid-stream")

    with pytest.raises(ConnectionError, match="reset mid-stream"):
        _run_stream_with_timeout(stream_fn)


def test_run_stream_times_out_when_stream_hangs():
    import time

    def stream_fn():
        time.sleep(5)
        yield _Chunk("too late")

    with pytest.raises(RuntimeError, match="流式调用超时"):
        _run_stream_with_timeout(stream_fn, join_timeout=0.2)


def test_run_stream_releases_semaphore_after_error():
    from utils.llm_utils import _LLM_SEMAPHORE

    def stream_fn():
        raise ValueError("bad stream")

    with pytest.raises(ValueError):
        _run_stream_with_timeout(stream_fn)

    # 异常路径也必须释放信号量
    assert _LLM_SEMAPHORE.acquire(timeout=0.5) is True
    _LLM_SEMAPHORE.release()
