import re
import math
from pathlib import Path
from typing import List, Dict, Set
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor


STOPWORDS: Set[str] = {
    '的', '了', '是', '在', '和', '与', '或', '以及', '等', '之', '于',
    '上', '下', '中', '为', '与', '其', '所', '以', '因', '对', '将',
    '可', '能', '会', '有', '也', '都', '而', '着', '到', '这', '那',
    '个', '一', '不', '就', '但', '又', '被', '从', '由', '向', '往',
    '如', '把', '让', '给', '用', '通过', '根据', '按照', '为了',
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
    'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
    'it', 'its', 'not', 'no', 'so', 'if', 'then', 'than'
}

MIN_WORD_LEN = 2
MAX_TAGS = 5
MIN_TF_IDF_SCORE = 0.01


def tokenize(text: str) -> List[str]:
    """中英文混合分词"""
    text = text.lower()
    words = []
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
    english_pattern = re.compile(r'[a-z]+')
    other = re.compile(r'[^\w]')

    pos = 0
    while pos < len(text):
        m = chinese_pattern.match(text, pos)
        if m:
            words.extend(list(m.group()))
            pos = m.end()
            continue
        m = english_pattern.match(text, pos)
        if m:
            words.append(m.group())
            pos = m.end()
            continue
        m = other.match(text, pos)
        if m:
            pos = m.end()
            continue
        words.append(text[pos])
        pos += 1

    return [w for w in words if len(w) >= MIN_WORD_LEN and w not in STOPWORDS]


def compute_tf(tokens: List[str]) -> Dict[str, float]:
    """计算词频 TF"""
    if not tokens:
        return {}
    freq = defaultdict(int)
    for t in tokens:
        freq[t] += 1
    total = len(tokens)
    return {t: count / total for t, count in freq.items()}


def compute_idf(documents: List[List[str]]) -> Dict[str, float]:
    """计算逆文档频率 IDF"""
    df = defaultdict(int)
    for tokens in documents:
        unique = set(tokens)
        for t in unique:
            df[t] += 1
    n = len(documents)
    return {t: math.log((n + 1) / (df[t] + 1)) for t in df}


def compute_tfidf(tf: Dict[str, float], idf: Dict[str, float]) -> Dict[str, float]:
    """计算 TF-IDF"""
    return {t: tf_val * idf.get(t, 0) for t, tf_val in tf.items()}


def extract_tags_from_text(text: str, idf: Dict[str, float] = None) -> List[str]:
    """从单篇文本提取标签"""
    tokens = tokenize(text)
    if not tokens:
        return []
    tf = compute_tf(tokens)
    if idf is None:
        documents = [tokens]
        idf = compute_idf(documents)
    tfidf = compute_tfidf(tf, idf)
    sorted_terms = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)
    tags = [term for term, score in sorted_terms if score >= MIN_TF_IDF_SCORE][:MAX_TAGS]
    return tags


def extract_tags_batch(
    texts: List[str],
    titles: List[str] = None,
    filenames: List[str] = None,
    n_workers: int = 4
) -> List[List[str]]:
    """
    批量提取多篇文档的标签（并行）。

    参数：
        texts: 文档文本列表，每项对应一篇文档
        titles: 文档标题列表（可选），与 texts 同索引
        filenames: 文件名列表（可选），用于从文件名中提取标签
        n_workers: 并行工作线程数，默认 4

    返回：
        二维列表，外层索引对应文档，内层为该文档的标签列表

    实现说明：
        - 基于 TF-IDF 算法，先对所有文档统一计算 IDF 值，再逐篇计算 TF-IDF
        - 支持从标题和文件名中补充提取标签（权重叠加后去重）
        - 使用 ThreadPoolExecutor 并行处理，提升大批量文档的处理速度

    未使用说明：
        当前项目中使用的是 process_and_tag_file（单文件串行），
        本函数设计用于需要一次性处理大量文档并需要并行加速的场景。
        保留以备未来批量处理需求。
    """
    if not texts:
        return [[] for _ in texts]

    all_tokens = [tokenize(t) for t in texts]
    idf = compute_idf(all_tokens)

    def process_one(idx: int) -> List[str]:
        tokens = all_tokens[idx]
        tf = compute_tf(tokens)
        tfidf = compute_tfidf(tf, idf)
        sorted_terms = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)
        tags = [term for term, score in sorted_terms if score >= MIN_TF_IDF_SCORE][:MAX_TAGS]

        title_extra = []
        if titles and idx < len(titles):
            title_extra = extract_tags_from_text(titles[idx], idf)

        filename_extra = []
        if filenames and idx < len(filenames):
            filename_extra = extract_tags_from_text(filenames[idx], idf)

        all_tags = tags + title_extra + filename_extra
        seen = set()
        unique_tags = []
        for tag in all_tags:
            if tag not in seen and len(unique_tags) < MAX_TAGS:
                seen.add(tag)
                unique_tags.append(tag)
        return unique_tags

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        results = list(executor.map(process_one, range(len(texts))))
    return results


def append_tags_to_markdown(file_path: str, tags: List[str]):
    """
    将标签追加到 Markdown 文件末尾。

    参数：
        file_path: Markdown 文件路径
        tags: 标签列表

    实现说明：
        - 在文件末尾追加 `*标签: tag1, tag2, ...*` 格式行
        - 若文件中已存在标签行，则替换旧标签而非追加
        - 使用 `---` 分隔符与正文区分

    未使用说明：
        当前项目中 process_and_tag_file 函数直接修改文件内容添加标签，
        未调用本函数。本函数适用于需要将标签追加到文件末尾的独立工具场景。
        保留以备未来工具化使用。
    """
    if not tags:
        return
    p = Path(file_path)
    if not p.exists():
        return
    content = p.read_text(encoding='utf-8')
    tag_line = '\n\n---\n*标签: ' + ', '.join(tags) + '*\n'
    if '*标签:' in content:
        existing_tag_pattern = re.compile(r'\*标签:.*?\*\n?', re.DOTALL)
        content = existing_tag_pattern.sub(tag_line.strip(), content)
    else:
        content += tag_line
    p.write_text(content, encoding='utf-8')


def process_and_tag_file(file_path: str, idf: Dict[str, float] = None) -> List[str]:
    """处理单个文件并打标签"""
    p = Path(file_path)
    if not p.exists() or not p.suffix.lower() == '.md':
        return []
    content = p.read_text(encoding='utf-8')
    tags = extract_tags_from_text(content, idf)
    if tags:
        append_tags_to_markdown(str(p), tags)
    return tags


def tag_markdown_files(
    file_paths: List[str],
    all_texts: List[str] = None,
    titles: List[str] = None
) -> Dict[str, List[str]]:
    """对一批 Markdown 文件进行标签提取和追加"""
    if not file_paths:
        return {}

    if all_texts and len(all_texts) == len(file_paths):
        texts = all_texts
    else:
        texts = []
        for fp in file_paths:
            try:
                texts.append(Path(fp).read_text(encoding='utf-8'))
            except Exception:
                texts.append('')

    if titles is None:
        titles = []
        for fp in file_paths:
            try:
                from utils.helpers import extract_title_from_markdown
                content = Path(fp).read_text(encoding='utf-8') if fp not in texts else texts[file_paths.index(fp)]
                titles.append(extract_title_from_markdown(content) or Path(fp).stem)
            except Exception:
                titles.append(Path(fp).stem)

    all_tokens = [tokenize(t) for t in texts]
    idf = compute_idf(all_tokens)

    results = {}
    for i, fp in enumerate(file_paths):
        try:
            tf = compute_tf(all_tokens[i])
            tfidf = compute_tfidf(tf, idf)
            sorted_terms = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)
            tags = [term for term, score in sorted_terms if score >= MIN_TF_IDF_SCORE][:MAX_TAGS]

            title_extra = extract_tags_from_text(titles[i], idf)
            all_tags = tags + title_extra
            seen = set()
            unique_tags = []
            for tag in all_tags:
                if tag not in seen and len(unique_tags) < MAX_TAGS:
                    seen.add(tag)
                    unique_tags.append(tag)

            if unique_tags:
                append_tags_to_markdown(str(fp), unique_tags)
                results[str(fp)] = unique_tags
        except Exception:
            pass

    return results
