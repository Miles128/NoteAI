"""Stable identifiers used by the semantic compiler."""

from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Normalize insignificant whitespace without changing semantic content."""
    return _WHITESPACE.sub(" ", value).strip()


def stable_id(kind: str, *parts: str, length: int = 24) -> str:
    payload = "\x1f".join(normalize_text(str(part)) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]
    return f"{kind}_{digest}"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
