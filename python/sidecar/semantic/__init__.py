"""Evidence-first semantic compilation for NoteAI source notes."""

from sidecar.semantic.claim_verifier import (
    build_cli_research_prompt,
    check_cli_agent,
    parse_verification_json,
    verdict_label,
    verify_claim_via_cli,
    verify_statement_via_cli,
)
from sidecar.semantic.compiler import compile_note_semantics
from sidecar.semantic.extractor import extract_document_semantics
from sidecar.semantic.parser import SemanticBlock, parse_semantic_blocks
from sidecar.semantic.store import SemanticStore
from sidecar.semantic.topic_state import build_topic_state, materialize_topic_state

__all__ = [
    "SemanticBlock",
    "SemanticStore",
    "build_cli_research_prompt",
    "check_cli_agent",
    "compile_note_semantics",
    "extract_document_semantics",
    "parse_semantic_blocks",
    "parse_verification_json",
    "verify_claim_via_cli",
    "verify_statement_via_cli",
    "verdict_label",
    "build_topic_state",
    "materialize_topic_state",
]
