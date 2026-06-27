"""Tests for the unified error handling utilities."""

import logging

import pytest

from utils.error_handler import format_exc_compact, log_exception, swallow


class TestLogException:
    def test_info_level_does_not_raise(self):
        logger = logging.getLogger("test.error_handler.info")
        try:
            raise ValueError("boom")
        except ValueError as e:
            log_exception("test context", e, level="info", logger=logger)

    def test_unknown_level_falls_back_to_warning(self, caplog):
        logger = logging.getLogger("test.error_handler.unknown")
        with caplog.at_level(logging.WARNING, logger="test.error_handler.unknown"):
            log_exception("fallback", level="not-a-level", logger=logger)
        assert any("fallback" in r.message for r in caplog.records)


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
