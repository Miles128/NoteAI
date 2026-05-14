"""Tests for the unified error handling utilities."""

import sys
import pytest
from utils.error_handler import log_exception, swallow, format_exc_compact


class TestFormatExcCompact:
    def test_formats_exception(self):
        try:
            raise ValueError("test message")
        except ValueError as e:
            s = format_exc_compact(e)
            assert "ValueError" in s
            assert "test message" in s

    def test_no_traceback(self):
        e = RuntimeError("no tb")
        s = format_exc_compact(e)
        assert s == "RuntimeError: no tb"


class TestSwallowDecorator:
    def test_catches_and_returns_default(self):
        @swallow("op failed", default=42)
        def fail():
            raise RuntimeError("boom")

        assert fail() == 42

    def test_reraises_specified(self):
        @swallow("op failed", default=42, reraise=(RuntimeError,))
        def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            fail()

    def test_passes_through_success(self):
        @swallow("op failed", default=42)
        def ok():
            return "yes"

        assert ok() == "yes"
