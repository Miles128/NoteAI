"""Topic folder path helpers (Notes/ and wiki artifact dirs)."""

from __future__ import annotations

from pathlib import Path

from config import config
from config.constants import TOPIC_SEP


def topic_notes_dir(workspace_path: Path, topic_name: str) -> Path:
    normalized = topic_name.replace("/", TOPIC_SEP)
    parts = [p.strip() for p in normalized.split(TOPIC_SEP) if p.strip()]
    topic_dir = workspace_path / config.NOTES_FOLDER
    for part in parts:
        topic_dir = topic_dir / part
    return topic_dir


def topic_artifact_dir(workspace_path: Path, root_folder: str, topic_name: str) -> Path:
    normalized = topic_name.replace("/", TOPIC_SEP)
    parts = [p.strip() for p in normalized.split(TOPIC_SEP) if p.strip()]
    topic_dir = workspace_path / root_folder
    for part in parts:
        topic_dir = topic_dir / part
    return topic_dir
