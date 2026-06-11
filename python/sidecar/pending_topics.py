"""Compatibility wrapper for pending topic suggestions.

The canonical implementation lives in utils.topic_pending so all callers share
the same locking and atomic-write behavior.
"""

from pathlib import Path

from utils.topic_pending import get_pending_path, load_pending, save_pending


def get_pending_topics_path() -> Path | None:
    return get_pending_path()


def load_pending_topics() -> list:
    return load_pending()


def save_pending_topics(pending: list) -> None:
    save_pending(pending)
