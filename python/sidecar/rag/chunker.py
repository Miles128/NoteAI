import hashlib
import re

from sidecar.textutils import parse_frontmatter

MAX_CHUNK_CHARS = 1000


def chunk_file(file_path: str, text: str) -> list:
    meta, body = parse_frontmatter(text)
    if meta is None:
        meta = {}
        body = text

    topic = meta.get("topic") or ""
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip().strip("'\"") for t in tags.split(",") if t.strip()]
    elif not isinstance(tags, list):
        tags = []

    chunks = _split_by_headings(body, file_path, topic, tags)
    return chunks


def _split_by_headings(body: str, file_path: str, topic, tags) -> list:
    h2_pattern = re.compile(r"^(## .+)$", re.MULTILINE)
    splits = h2_pattern.split(body)

    chunks = []
    if splits and splits[0].strip():
        _add_chunks(splits[0], file_path, topic, tags, None, chunks)

    for i in range(1, len(splits), 2):
        heading = splits[i].strip() if i < len(splits) else ""
        content = splits[i + 1] if i + 1 < len(splits) else ""
        section_title = re.sub(r"^##\s*", "", heading)
        if content.strip():
            _add_chunks(content, file_path, topic, tags, section_title, chunks)

    return chunks


def _add_chunks(content: str, file_path: str, topic, tags, section_title, chunks):
    if len(content) <= MAX_CHUNK_CHARS:
        chunks.append(_make_chunk(content, file_path, topic, tags, section_title))
        return

    h3_pattern = re.compile(r"^(### .+)$", re.MULTILINE)
    splits = h3_pattern.split(content)

    if len(splits) > 1:
        if splits[0].strip():
            _add_paragraph_chunks(splits[0], file_path, topic, tags, section_title, chunks)
        for i in range(1, len(splits), 2):
            heading = splits[i].strip() if i < len(splits) else ""
            sub_content = splits[i + 1] if i + 1 < len(splits) else ""
            sub_title = re.sub(r"^###\s*", "", heading)
            full_title = f"{section_title} > {sub_title}" if section_title else sub_title
            if sub_content.strip():
                _add_paragraph_chunks(sub_content, file_path, topic, tags, full_title, chunks)
    else:
        _add_paragraph_chunks(content, file_path, topic, tags, section_title, chunks)


def _add_paragraph_chunks(content: str, file_path: str, topic, tags, section_title, chunks):
    if len(content) <= MAX_CHUNK_CHARS:
        chunks.append(_make_chunk(content, file_path, topic, tags, section_title))
        return

    paragraphs = re.split(r"\n{2,}", content)
    current = ""
    for para in paragraphs:
        if not para.strip():
            continue
        if len(current) + len(para) + 2 > MAX_CHUNK_CHARS and current:
            chunks.append(_make_chunk(current, file_path, topic, tags, section_title))
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(_make_chunk(current, file_path, topic, tags, section_title))


def _make_chunk(content: str, file_path: str, topic, tags, section_title) -> dict:
    chunk_id = hashlib.md5(f"{file_path}::{section_title or ''}::{content[:100]}".encode()).hexdigest()[:12]
    return {
        "id": chunk_id,
        "content": content.strip(),
        "file_path": file_path,
        "topic": topic,
        "tags": tags,
        "section_title": section_title,
    }
