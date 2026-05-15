import hashlib
import re

from sidecar.textutils import parse_frontmatter

MAX_CHUNK_CHARS = 1000
OVERLAP_MIN_CHARS = 100
OVERLAP_RATIO = 0.2


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

    segments = _split_into_segments(content)
    overlap_size = max(OVERLAP_MIN_CHARS, int(MAX_CHUNK_CHARS * OVERLAP_RATIO))

    current = ""
    for seg in segments:
        seg_stripped = seg.strip()
        if not seg_stripped:
            continue

        if _is_table(seg_stripped):
            if current:
                chunks.append(_make_chunk(current, file_path, topic, tags, section_title))
                if len(current) > overlap_size:
                    current = current[-overlap_size:]
                else:
                    current = ""
            chunks.append(_make_chunk(seg_stripped, file_path, topic, tags, section_title))
            continue

        if _is_code_block(seg_stripped):
            if current:
                chunks.append(_make_chunk(current, file_path, topic, tags, section_title))
                if len(current) > overlap_size:
                    current = current[-overlap_size:]
                else:
                    current = ""
            chunks.append(_make_chunk(seg_stripped, file_path, topic, tags, section_title))
            continue

        if len(current) + len(seg) + 2 > MAX_CHUNK_CHARS and current:
            chunks.append(_make_chunk(current, file_path, topic, tags, section_title))
            if len(current) > overlap_size:
                current = current[-overlap_size:] + "\n\n" + seg
            else:
                current = seg
        else:
            current = current + "\n\n" + seg if current else seg

    if current.strip():
        chunks.append(_make_chunk(current, file_path, topic, tags, section_title))


def _split_into_segments(content: str) -> list:
    segments = []
    code_pattern = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)
    table_pattern = re.compile(r"(\|.*\|(\n\|[-:|]+\|)?(\n\|.*\|)*)", re.MULTILINE)

    pos = 0
    while pos < len(content):
        code_match = code_pattern.search(content, pos)
        table_match = table_pattern.search(content, pos)

        next_code_pos = code_match.start() if code_match else float('inf')
        next_table_pos = table_match.start() if table_match else float('inf')

        if next_code_pos < next_table_pos:
            if next_code_pos > pos:
                segments.append(content[pos:next_code_pos])
            segments.append(code_match.group(1))
            pos = code_match.end()
        elif next_table_pos < next_code_pos:
            if next_table_pos > pos:
                segments.append(content[pos:next_table_pos])
            segments.append(table_match.group(1))
            pos = table_match.end()
        else:
            paragraphs = re.split(r"\n{2,}", content[pos:])
            segments.extend(paragraphs)
            break

    return segments


def _is_table(text: str) -> bool:
    lines = text.strip().split('\n')
    if len(lines) < 2:
        return False

    first_line = lines[0].strip()
    if not first_line.startswith('|') or not first_line.endswith('|'):
        return False

    if len(lines) >= 2:
        second_line = lines[1].strip()
        if second_line.startswith('|') and re.match(r'^\|[-:|]+\|$', second_line):
            return True

    return False


def _is_code_block(text: str) -> bool:
    text = text.strip()
    return text.startswith('```') and text.endswith('```')


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
