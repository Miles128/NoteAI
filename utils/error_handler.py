"""Unified error handling utilities for NoteAI."""

import functools
import logging
import traceback
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

_log = logging.getLogger("NoteAI")


def log_exception(
    context: str = "",
    exc: Optional[Exception] = None,
    level: str = "warning",
    *,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Log an exception with context. Use in except blocks instead of bare pass.

    Args:
        context: Description of the operation that failed.
        exc: The caught exception (for logging the original message).
        level: Log level: 'debug', 'warning', or 'error'.
        logger: Custom logger instance (uses module default if None).
    """
    use_logger = logger or _log
    msg = f"[non-critical] {context}"
    if exc:
        msg += f": {exc}"

    log_fn = {"debug": use_logger.debug, "warning": use_logger.warning, "error": use_logger.error}[level]
    log_fn(msg)


def swallow(
    context: str = "",
    level: str = "warning",
    *,
    default: T = None,
    logger: Optional[logging.Logger] = None,
    reraise: Optional[tuple[type[Exception], ...]] = None,
) -> Callable:
    """Decorator that catches exceptions, logs them, and returns a default value.

    Example:
        @swallow("failed to parse config", level="debug", default={})
        def parse_config(path):
            return json.loads(Path(path).read_text())
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if reraise and isinstance(e, reraise):
                    raise
                log_exception(context, e, level=level, logger=logger)
                return default

        return wrapper

    return decorator


def log_and_reraise(
    context: str = "",
    *,
    logger: Optional[logging.Logger] = None,
    wrap_exc: Optional[type[Exception]] = None,
) -> Callable:
    """Decorator that logs an exception then re-raises it (optionally wrapped).

    Example:
        @log_and_reraise("RAG retrieval failed", wrap_exc=RuntimeError)
        def retrieve(query):
            ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                log_exception(context, e, level="error", logger=logger)
                if wrap_exc:
                    raise wrap_exc(str(e)) from e
                raise

        return wrapper

    return decorator


def format_exc_compact(exc: Exception) -> str:
    """Return a compact error summary (type + message + last frame)."""
    tb = traceback.extract_tb(exc.__traceback__)
    last_frame = f" ({tb[-1].filename}:{tb[-1].lineno})" if tb else ""
    return f"{type(exc).__name__}: {exc}{last_frame}"
