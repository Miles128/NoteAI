"""Shared frontmatter / text helpers for sidecar handlers.

Canonical implementation lives in utils/text_utils.py; this module re-exports
it for backward compatibility with existing `from sidecar.textutils import ...`
call sites.
"""

from utils.text_utils import (  # noqa: F401
    parse_frontmatter,
    write_frontmatter,
)
