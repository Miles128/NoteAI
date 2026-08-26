"""Evidence-first semantic compilation for NoteAI source notes."""

from sidecar.semantic.compiler import compile_note_semantics
from sidecar.semantic.extractor import extract_document_semantics
from sidecar.semantic.parser import SemanticBlock, parse_semantic_blocks
from sidecar.semantic.store import SemanticStore
from sidecar.semantic.topic_state import build_topic_state, materialize_topic_state

__all__ = [
    "SemanticBlock",
    "SemanticStore",
    "compile_note_semantics",
    "extract_document_semantics",
    "parse_semantic_blocks",
    "build_topic_state",
    "materialize_topic_state",
]
