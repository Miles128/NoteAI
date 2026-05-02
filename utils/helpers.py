"""通用工具函数"""

import re
import os
import hashlib
from pathlib import Path
from typing import Optional, List
import unicodedata


# 从子模块 re-export，保持向后兼容
from utils.llm_utils import (
    APIConfigError,
    NetworkError,
    is_network_error,
    _create_llm,
    call_llm,
    call_llm_raw,
    check_api_config,
    test_api_connection,
    _estimate_tokens,
    summarize_with_llm,
    compress_with_llm,
    process_content_with_llm,
    reformat_markdown_with_llm,
)
from utils.pdf_utils import extract_pdf_text, extract_pdf_pages


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """清理文件名，移除非法字符"""
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = ''.join(char for char in filename if unicodedata.category(char)[0] != 'C')
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    filename = filename.strip(' .')
    return filename or "unnamed"


def generate_hash(content: str, length: int = 8) -> str:
    """生成内容哈希"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:length]


def clean_text(text: str) -> str:
    """清理文本内容"""
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = re.sub(r'[​-‏﻿]', '', line)
        line = re.sub(r'[ \t]+', ' ', line)
        cleaned_lines.append(line.strip())
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    return text.strip()


def remove_images_from_markdown(md_content: str) -> str:
    """从Markdown中移除图片"""
    md_content = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', md_content)
    md_content = re.sub(r'<img[^>]+>', '', md_content, flags=re.IGNORECASE)
    md_content = re.sub(r'\[([^\]]+)\]:\s*\S+\.(?:png|jpg|jpeg|gif|webp|svg)\s*\n?', '', md_content, flags=re.IGNORECASE)
    return md_content


def extract_title_from_markdown(md_content: str) -> Optional[str]:
    """从Markdown内容中提取标题"""
    lines = md_content.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('# '):
            return line[2:].strip()
        if line.startswith('## '):
            return line[3:].strip()
    return None


def split_text_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """将文本分割成块"""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            for i in range(end, start, -1):
                if text[i - 1] in '.。!！?？\n':
                    end = i
                    break

        chunks.append(text[start:end].strip())
        start = end - overlap

    return chunks


def recursive_markdown_chunk(text: str, chunk_size: int = 1000, overlap: int = 200, current_heading: str = "") -> List[str]:
    """递归Markdown切片：按照标题层级、标点符号层层切片"""
    if len(text) <= chunk_size:
        if current_heading and not text.startswith('#'):
            return [f"{current_heading}\n\n{text}"]
        return [text]

    chunks = []
    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    headings = list(heading_pattern.finditer(text))

    if len(headings) > 1:
        for i in range(len(headings)):
            start_pos = headings[i].start()
            end_pos = headings[i + 1].start() if i + 1 < len(headings) else len(text)

            section = text[start_pos:end_pos].strip()
            heading_line = headings[i].group(0)
            section_content = text[headings[i].end():end_pos].strip()

            if len(section) > chunk_size:
                sub_chunks = recursive_markdown_chunk(
                    section_content, chunk_size, overlap,
                    current_heading=heading_line
                )
                chunks.extend(sub_chunks)
            else:
                if current_heading:
                    if not section.startswith('#'):
                        section = f"{current_heading}\n\n{section}"
                    else:
                        section = f"{current_heading}\n{section}"
                chunks.append(section)
    elif len(headings) == 1:
        heading_line = headings[0].group(0)
        content_after_heading = text[headings[0].end():].strip()

        if len(content_after_heading) <= chunk_size:
            full_section = f"{heading_line}\n\n{content_after_heading}"
            if current_heading:
                full_section = f"{current_heading}\n{full_section}"
            chunks.append(full_section)
        else:
            sub_chunks = recursive_markdown_chunk(
                content_after_heading, chunk_size, overlap,
                current_heading=heading_line
            )
            chunks.extend(sub_chunks)
    else:
        paragraphs = re.split(r'\n\n+', text)

        if len(paragraphs) > 1 and any(len(p) > chunk_size for p in paragraphs):
            current_chunk = ""
            for para in paragraphs:
                if len(current_chunk) + len(para) + 2 > chunk_size:
                    if current_chunk:
                        if current_heading and not current_chunk.startswith('#'):
                            current_chunk = f"{current_heading}\n\n{current_chunk}"
                        chunks.append(current_chunk.strip())

                    if len(para) > chunk_size:
                        sub_chunks = _split_by_punctuation(para, chunk_size, overlap, current_heading)
                        chunks.extend(sub_chunks)
                        current_chunk = ""
                    else:
                        current_chunk = para
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + para
                    else:
                        current_chunk = para

            if current_chunk:
                if current_heading and not current_chunk.startswith('#'):
                    current_chunk = f"{current_heading}\n\n{current_chunk}"
                chunks.append(current_chunk.strip())
        else:
            sub_chunks = _split_by_punctuation(text, chunk_size, overlap, current_heading)
            chunks.extend(sub_chunks)

    return chunks


def _split_by_punctuation(text: str, chunk_size: int, overlap: int, current_heading: str = "") -> List[str]:
    """按标点符号分割文本（递归切片的最后一层）"""
    if len(text) <= chunk_size:
        if current_heading and not text.startswith('#'):
            return [f"{current_heading}\n\n{text}"]
        return [text]

    chunks = []
    punctuation_patterns = [
        r'[.。!！?？]',
        r'[;；]',
        r'[，,]',
        r'\n',
    ]

    split_pos = None
    for pattern in punctuation_patterns:
        matches = list(re.finditer(pattern, text))
        if matches:
            target_pos = chunk_size
            for match in reversed(matches):
                if match.end() <= target_pos:
                    split_pos = match.end()
                    break
            if split_pos:
                break

    if split_pos is None:
        split_pos = min(chunk_size, len(text))

    chunk = text[:split_pos].strip()
    if current_heading and not chunk.startswith('#'):
        chunk = f"{current_heading}\n\n{chunk}"
    chunks.append(chunk)

    remaining_start = split_pos - overlap
    if remaining_start >= split_pos:
        remaining_start = split_pos

    remaining = text[remaining_start:].strip()

    if remaining and len(remaining) < len(text):
        sub_chunks = _split_by_punctuation(remaining, chunk_size, overlap, current_heading)
        chunks.extend(sub_chunks)

    return chunks


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


def ensure_dir(path: str) -> Path:
    """确保目录存在"""
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def is_valid_url(url: str) -> bool:
    """验证URL是否有效"""
    try:
        import validators
        return validators.url(url) is True
    except ImportError:
        pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return bool(pattern.match(url))


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def get_file_extension(filename: str) -> str:
    """获取文件扩展名"""
    return Path(filename).suffix.lower()


def read_file_with_encoding(file_path: str, encodings: List[str] = None) -> str:
    """尝试多种编码读取文件"""
    if encodings is None:
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue

    raise RuntimeError(f"无法使用任何编码读取文件: {file_path}")


def validate_api_key(api_key: str) -> bool:
    """验证 API Key 是否有效"""
    if not api_key or not api_key.strip():
        return False
    api_key = api_key.strip()
    if len(api_key) < 10:
        return False
    return True


def detect_language(text: str) -> str:
    """简单检测文本语言"""
    if not text:
        return 'unknown'
    chinese_chars = sum(1 for char in text if '一' <= char <= '鿿')
    total_chars = len(text)
    if total_chars == 0:
        return 'unknown'
    chinese_ratio = chinese_chars / total_chars
    if chinese_ratio > 0.3:
        return 'chinese'
    return 'english'


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    import time
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator


def smart_truncate_text(text: str, max_length: int = 1000, suffix: str = "...") -> str:
    """智能截断文本，遵循重要信息优先保留原则"""
    if len(text) <= max_length:
        return text

    available_length = max_length - len(suffix)

    lines = text.split('\n')
    result_lines = []
    current_length = 0
    found_content_start = False

    for line in lines:
        line_length = len(line) + 1

        if line.strip().startswith('#'):
            result_lines.append(line)
            current_length += line_length
            found_content_start = True
        elif not found_content_start and line.strip() == '':
            result_lines.append(line)
            current_length += line_length
        else:
            if current_length + line_length <= available_length:
                result_lines.append(line)
                current_length += line_length
                found_content_start = True
            else:
                remaining = available_length - current_length
                if remaining > 50:
                    truncated_line = _truncate_at_sentence_boundary(line, remaining)
                    result_lines.append(truncated_line)
                break

    result = '\n'.join(result_lines)

    if len(result) > max_length:
        result = result[:available_length]

    result = result.rstrip() + suffix

    return result


def _truncate_at_sentence_boundary(text: str, max_length: int) -> str:
    """在句子边界处截断文本"""
    if len(text) <= max_length:
        return text

    boundary_chars = ['.', '。', '!', '！', '?', '？', '\n']

    best_pos = max_length
    for i in range(max_length, 0, -1):
        if text[i - 1] in boundary_chars:
            best_pos = i
            break

    return text[:best_pos]


def clean_markdown_content(content: str) -> str:
    """清理 Markdown 内容，移除乱码、冗余格式"""
    if not content:
        return content

    lines = content.split('\n')
    cleaned_lines = []
    prev_line_empty = False

    for line in lines:
        line = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', line)
        line = re.sub(r'[​-‏﻿]', '', line)

        is_empty = not line.strip()

        if is_empty:
            if not prev_line_empty:
                cleaned_lines.append('')
                prev_line_empty = True
            continue

        line = re.sub(r'[ \t]+', ' ', line)
        line = line.rstrip()

        cleaned_lines.append(line)
        prev_line_empty = False

    result = '\n'.join(cleaned_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()


def optimize_markdown_format(content: str, title: str = "") -> str:
    """优化 Markdown 格式"""
    if not content:
        return content

    content = clean_markdown_content(content)

    lines = content.split('\n')
    result_lines = []
    found_h1 = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('#'):
            heading_match = re.match(r'^(#{1,6})\s+(.*)$', stripped)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                if level == 1:
                    found_h1 = True
                result_lines.append(f"{'#' * level} {text}")
                continue

        if stripped.startswith('- ') or stripped.startswith('* '):
            result_lines.append('- ' + stripped[2:])
            continue

        if re.match(r'^\d+\.\s', stripped):
            result_lines.append(stripped)
            continue

        if stripped.startswith('```'):
            result_lines.append(stripped)
            continue

        result_lines.append(line)

    result = '\n'.join(result_lines)

    if not found_h1 and title:
        if result.strip():
            result = f"# {title}\n\n{result}"

    return result


def smart_format_markdown(content: str, title: str = "") -> str:
    """智能格式化 Markdown：小文档用 LLM，大文档用规则"""
    if not content or not content.strip():
        return content

    content = clean_markdown_content(content)

    h2_count = len(re.findall(r'^##\s+', content, re.MULTILINE))

    if h2_count >= 2:
        return content

    from config.settings import config
    if config.api_key:
        result = reformat_markdown_with_llm(content)
        if result != content:
            return result

    return optimize_markdown_format(content, title)
