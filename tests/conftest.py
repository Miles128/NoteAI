"""Global test setup.

Unit tests must never reach the real LLM API: with the AI master switch forced
off, code paths like the conversion LLM rewrite short-circuit before any
network I/O. Tests that intentionally exercise AI-gate behavior (test_ai_gate)
re-enable it on their own via monkeypatch, which runs after this fixture.
"""

from __future__ import annotations

import pytest

from config import config


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ai_enabled", False, raising=False)
