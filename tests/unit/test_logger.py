from unittest.mock import Mock

from utils.logger import AppLogger


def test_logger_forwards_standard_format_arguments(monkeypatch) -> None:
    app_logger = AppLogger()
    info = Mock()
    monkeypatch.setattr(app_logger.logger, "info", info)

    app_logger.info("component %s: %s", "rag", "installed", extra={"source": "test"})

    info.assert_called_once_with(
        "component %s: %s",
        "rag",
        "installed",
        extra={"source": "test"},
    )


def test_logger_exposes_exception_api(monkeypatch) -> None:
    app_logger = AppLogger()
    exception = Mock()
    monkeypatch.setattr(app_logger.logger, "exception", exception)

    app_logger.exception("task %s failed", "ingest")

    exception.assert_called_once_with("task %s failed", "ingest")
