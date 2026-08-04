"""Deterministic Markdown-to-block parser for semantic compilation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sidecar.semantic.ids import content_hash, normalize_text, stable_id

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")


@dataclass(frozen=True)
class SemanticBlock:
    id: str
    block_type: str
    heading_path: tuple[str, ...]
    ordinal: int
    content: str
    content_hash: str
    start_line: int
    end_line: int


def _body_lines(markdown: str) -> tuple[list[str], int]:
    """Return body lines and their one-based line offset in the source file."""
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return lines, 1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[index + 1 :], index + 2
    return lines, 1


def _classify(lines: list[str]) -> str:
    stripped = [line.strip() for line in lines if line.strip()]
    if not stripped:
        return "paragraph"
    if stripped[0].startswith("```"):
        return "code"
    if len(stripped) >= 2 and "|" in stripped[0] and _TABLE_SEPARATOR.match(stripped[1]):
        return "table"
    if all(re.match(r"^(?:[-+*]|\d+[.)])\s+", line) for line in stripped):
        return "list"
    if stripped[0].startswith(">"):
        return "quote"
    return "paragraph"


def parse_semantic_blocks(document_id: str, markdown: str) -> list[SemanticBlock]:
    """Split Markdown into stable, source-located semantic blocks.

    Headings define structural paths but are not emitted as evidence blocks.
    Block identity depends on document, heading path, type, normalized content,
    and duplicate occurrence within that path. Unrelated insertions therefore do
    not renumber unchanged blocks.
    """
    lines, first_line = _body_lines(markdown)
    headings: list[str] = []
    raw_blocks: list[tuple[str, tuple[str, ...], str, int, int]] = []
    buffer: list[str] = []
    buffer_start = first_line
    in_fence = False

    def flush(end_line: int) -> None:
        nonlocal buffer
        while buffer and not buffer[0].strip():
            buffer.pop(0)
            buffer_start_adjusted = 1
            # Keep the source line correct after leading blank lines.
            nonlocal buffer_start
            buffer_start += buffer_start_adjusted
        while buffer and not buffer[-1].strip():
            buffer.pop()
            end_line -= 1
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        raw_blocks.append((_classify(buffer), tuple(headings), text, buffer_start, end_line))
        buffer = []

    for offset, line in enumerate(lines):
        line_no = first_line + offset
        stripped = line.strip()
        if stripped.startswith("```"):
            if not buffer:
                buffer_start = line_no
            buffer.append(line)
            in_fence = not in_fence
            if not in_fence:
                flush(line_no)
            continue
        if in_fence:
            buffer.append(line)
            continue

        heading = _HEADING.match(line)
        if heading:
            flush(line_no - 1)
            level = len(heading.group(1))
            title = normalize_text(heading.group(2))
            headings[:] = headings[: level - 1]
            headings.append(title)
            buffer_start = line_no + 1
            continue

        if not stripped:
            flush(line_no - 1)
            buffer_start = line_no + 1
            continue

        if not buffer:
            buffer_start = line_no
        buffer.append(line)

    flush(first_line + len(lines) - 1)

    occurrences: dict[tuple[tuple[str, ...], str, str], int] = {}
    blocks: list[SemanticBlock] = []
    for ordinal, (block_type, path, text, start, end) in enumerate(raw_blocks):
        normalized = normalize_text(text)
        digest = content_hash(normalized)
        occurrence_key = (path, block_type, digest)
        occurrence = occurrences.get(occurrence_key, 0)
        occurrences[occurrence_key] = occurrence + 1
        block_id = stable_id(
            "blk",
            document_id,
            " > ".join(path),
            block_type,
            digest,
            str(occurrence),
        )
        blocks.append(
            SemanticBlock(
                id=block_id,
                block_type=block_type,
                heading_path=path,
                ordinal=ordinal,
                content=text,
                content_hash=digest,
                start_line=start,
                end_line=end,
            )
        )
    return blocks
