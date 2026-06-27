"""Structured error codes for NoteAI RPC layer.

All errors returned through the JSON-RPC channel carry a machine-readable code
plus a human-safe message.  The frontend can key on `code` for i18n and user
experience decisions (retry, show install prompt, etc.).
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    OK = "OK"

    # --- Generic ---
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    INVALID_PARAMS = "INVALID_PARAMS"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    METHOD_NOT_FOUND = "METHOD_NOT_FOUND"
    OPERATION_CANCELLED = "OPERATION_CANCELLED"
    TIMEOUT = "TIMEOUT"

    # --- Path / workspace ---
    WORKSPACE_NOT_SET = "WORKSPACE_NOT_SET"
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    PATH_OUTSIDE_WORKSPACE = "PATH_OUTSIDE_WORKSPACE"
    PATH_INVALID = "PATH_INVALID"
    PATH_CONTAINS_ILLEGAL_CHARS = "PATH_CONTAINS_ILLEGAL_CHARS"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_READ_ONLY = "FILE_READ_ONLY"
    DIRECTORY_PROTECTED = "DIRECTORY_PROTECTED"

    # --- Auth / credentials ---
    API_KEY_MISSING = "API_KEY_MISSING"
    API_KEY_INVALID = "API_KEY_INVALID"
    API_CONNECTION_FAILED = "API_CONNECTION_FAILED"
    CLOUD_AUTH_FAILED = "CLOUD_AUTH_FAILED"
    CLOUD_NOT_CONNECTED = "CLOUD_NOT_CONNECTED"

    # --- RAG / indexing ---
    RAG_NOT_ENABLED = "RAG_NOT_ENABLED"
    RAG_INDEX_EMPTY = "RAG_INDEX_EMPTY"
    RAG_INDEX_BUILDING = "RAG_INDEX_BUILDING"
    RAG_RETRIEVAL_FAILED = "RAG_RETRIEVAL_FAILED"
    RAG_LLM_CALL_FAILED = "RAG_LLM_CALL_FAILED"
    RAG_RERANKER_UNAVAILABLE = "RAG_RERANKER_UNAVAILABLE"

    # --- Feature availability ---
    FEATURE_NOT_INSTALLED = "FEATURE_NOT_INSTALLED"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    CLI_AGENT_NOT_FOUND = "CLI_AGENT_NOT_FOUND"
    CLI_AGENT_EXEC_FAILED = "CLI_AGENT_EXEC_FAILED"

    # --- Schema / ingest ---
    SCHEMA_NOT_SETUP = "SCHEMA_NOT_SETUP"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    INGEST_IN_PROGRESS = "INGEST_IN_PROGRESS"
    INGEST_FAILED = "INGEST_FAILED"
    CONVERSION_FAILED = "CONVERSION_FAILED"

    # --- Validation ---
    PROMPT_EMPTY = "PROMPT_EMPTY"
    PROMPT_TOO_LONG = "PROMPT_TOO_LONG"
    PROMPT_INVALID = "PROMPT_INVALID"
    TOPIC_NOT_FOUND = "TOPIC_NOT_FOUND"
    TAG_INVALID = "TAG_INVALID"

    # --- Cloud sync ---
    CLOUD_PROVIDER_UNKNOWN = "CLOUD_PROVIDER_UNKNOWN"
    CLOUD_SYNC_IN_PROGRESS = "CLOUD_SYNC_IN_PROGRESS"
    CLOUD_SYNC_FAILED = "CLOUD_SYNC_FAILED"

    # --- UI / frontend ---
    NOT_RUNNING_IN_TAURI = "NOT_RUNNING_IN_TAURI"
    WINDOW_OPERATION_FAILED = "WINDOW_OPERATION_FAILED"


def make_error(
    code: ErrorCode,
    message: str = "",
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured error payload for the RPC response.

    Handlers can either:
      - raise NoteAIError(code, message) which the router catches and formats
      - return make_error(...) directly from a handler for expected failures
    """
    payload: dict[str, Any] = {"code": code.value, "message": message or code.value}
    if details:
        payload["details"] = details
    return payload


class NoteAIError(Exception):
    """Domain exception with a structured error code.

    The RPC router converts this into {"error": {code, message, details}}.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str = "",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message or code.value
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return make_error(self.code, self.message, details=self.details)
