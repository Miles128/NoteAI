"""Backward-compatible re-exports — prefer workspace_rules_validator."""

from sidecar.workspace_rules import load_workspace_rules as parse_schema_rules  # noqa: F401
from sidecar.workspace_rules_validator import (  # noqa: F401
    SchemaValidationError,
    allows_wiki_edit,
    check_notes_writable,
    check_schema_ready,
    check_wiki_writable,
    require_topic,
    topic_depth,
    validate_topic,
)
from sidecar.workspace_rules import needs_workspace_rules_setup as needs_schema_setup  # noqa: F401
