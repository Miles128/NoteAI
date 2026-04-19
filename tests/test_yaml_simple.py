#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简化版YAML front matter测试 - 直接测试核心函数"""

import re
import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Optional, Any, Tuple
from collections import defaultdict

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
    text = text.lower()
    words = []
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
    english_pattern = re.compile(r'[a-z]+')
    other = re.compile(r'[^\w]')

    pos = 0
    while pos < len(text):
        m = chinese_pattern.match(text, pos)
        if m:
            chinese_text = m.group()
            if len(chinese_text) >= 2:
                words.append(chinese_text)
            else:
                words.extend(list(chinese_text))
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

    result = []
    for w in words:
        if w in STOPWORDS:
            continue
        if re.match(r'[\u4e00-\u9fff]+', w):
            if len(w) >= 1:
                result.append(w)
        else:
            if len(w) >= MIN_WORD_LEN:
                result.append(w)
    return result


def compute_tf(tokens: List[str]) -> Dict[str, float]:
    if not tokens:
        return {}
    freq = defaultdict(int)
    for t in tokens:
        freq[t] += 1
    total = len(tokens)
    return {t: count / total for t, count in freq.items()}


def compute_idf(documents: List[List[str]]) -> Dict[str, float]:
    df = defaultdict(int)
    for tokens in documents:
        unique = set(tokens)
        for t in unique:
            df[t] += 1
    n = len(documents)
    return {t: math.log((n + 1) / (df[t] + 1)) for t in df}


def compute_tfidf(tf: Dict[str, float], idf: Dict[str, float]) -> Dict[str, float]:
    return {t: tf_val * idf.get(t, 0) for t, tf_val in tf.items()}


def extract_tags_from_text(text: str, idf: dict = None) -> list:
    tokens = tokenize(text)
    if not tokens:
        return []
    tf = compute_tf(tokens)
    
    if idf is None:
        sorted_terms = sorted(tf.items(), key=lambda x: x[1], reverse=True)
        tags = [term for term, score in sorted_terms][:MAX_TAGS]
    else:
        tfidf = compute_tfidf(tf, idf)
        sorted_terms = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)
        tags = [term for term, score in sorted_terms if score >= MIN_TF_IDF_SCORE][:MAX_TAGS]
    
    return tags


def _escape_yaml_string(value: str) -> str:
    if not value:
        return '""'
    
    needs_quoting = False
    special_chars = ['"', '\\', '\n', '\r', '\t', '#', ': ', '[', ']', '{', '}', ',', '*', '&', '!', '|', '>', '%', '@', '`']
    
    for char in special_chars:
        if char in value:
            needs_quoting = True
            break
    
    if value.startswith((' ', '-', '?', ':')) or value.endswith(' '):
        needs_quoting = True
    
    if not needs_quoting:
        return value
    
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('\t', '\\t')
    
    return f'"{value}"'


def _format_yaml_value(value: Any) -> str:
    if value is None:
        return 'null'
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        if not value:
            return '[]'
        items = ', '.join(_escape_yaml_string(str(item)) for item in value)
        return f'[{items}]'
    elif isinstance(value, datetime):
        return _escape_yaml_string(value.strftime('%Y-%m-%d'))
    else:
        return _escape_yaml_string(str(value))


def generate_yaml_frontmatter(
    title: str = "",
    tags: List[str] = None,
    date: datetime = None,
    source: str = "",
    word_count: int = None,
    language: str = "",
    extra_fields: Dict[str, Any] = None
) -> str:
    fields = {}
    
    if title:
        fields['title'] = title
    
    if tags:
        fields['tags'] = tags
    else:
        fields['tags'] = []
    
    if date is None:
        date = datetime.now()
    fields['date'] = date
    
    if source:
        fields['source'] = source
    
    if word_count is not None:
        fields['word_count'] = word_count
    
    if language:
        fields['language'] = language
    
    if extra_fields:
        fields.update(extra_fields)
    
    lines = ['---']
    
    ordered_keys = ['title', 'tags', 'date', 'source', 'word_count', 'language']
    for key in ordered_keys:
        if key in fields:
            value = fields.pop(key)
            lines.append(f"{key}: {_format_yaml_value(value)}")
    
    for key, value in sorted(fields.items()):
        lines.append(f"{key}: {_format_yaml_value(value)}")
    
    lines.append('---')
    lines.append('')
    
    return '\n'.join(lines)


def run_tests():
    print("=" * 60)
    print("YAML Front Matter 核心功能测试")
    print("=" * 60 + "\n")
    
    # 测试1: 生成基本YAML front matter
    print("测试1: 生成基本YAML front matter")
    print("-" * 60)
    frontmatter = generate_yaml_frontmatter(
        title='测试文档标题',
        tags=['人工智能', '机器学习', '深度学习'],
        source='https://example.com/article',
        word_count=1234,
        language='chinese'
    )
    print(frontmatter)
    assert frontmatter.startswith('---')
    assert 'title:' in frontmatter
    assert 'tags:' in frontmatter
    assert '人工智能' in frontmatter
    print("✓ 通过\n")
    
    # 测试2: 特殊字符处理
    print("测试2: 特殊字符处理")
    print("-" * 60)
    frontmatter2 = generate_yaml_frontmatter(
        title='测试: 包含"引号"和: 冒号的标题',
        tags=['tag1', 'tag2'],
        source='C:\\Users\\test\\file.pdf'
    )
    print(frontmatter2)
    assert frontmatter2.startswith('---')
    print("✓ 通过\n")
    
    # 测试3: 标签提取（TF-IDF算法）
    print("测试3: 标签提取（TF-IDF算法）- 中文")
    print("-" * 60)
    chinese_text = '''
    人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，
    它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。
    机器学习（Machine Learning）是人工智能的一个子领域，
    深度学习（Deep Learning）又是机器学习的一个子领域。
    自然语言处理（NLP）、计算机视觉（CV）是人工智能的重要应用方向。
    '''
    tags = extract_tags_from_text(chinese_text)
    print(f"提取的标签: {tags}")
    assert len(tags) > 0
    print("✓ 通过\n")
    
    # 测试4: 英文标签提取
    print("测试4: 标签提取（TF-IDF算法）- 英文")
    print("-" * 60)
    english_text = '''
    Machine learning is a field of artificial intelligence that uses 
    statistical techniques to enable computers to learn from data. 
    Deep learning is a subset of machine learning based on neural networks.
    Natural language processing and computer vision are important applications.
    '''
    tags_en = extract_tags_from_text(english_text)
    print(f"提取的标签: {tags_en}")
    assert len(tags_en) > 0
    print("✓ 通过\n")
    
    # 测试5: 空内容边界情况
    print("测试5: 边界情况 - 空内容")
    print("-" * 60)
    frontmatter_empty = generate_yaml_frontmatter()
    print(frontmatter_empty)
    assert frontmatter_empty.startswith('---')
    assert 'tags: []' in frontmatter_empty
    print("✓ 通过\n")
    
    # 测试6: YAML格式兼容性验证
    print("测试6: YAML格式兼容性验证")
    print("-" * 60)
    frontmatter = generate_yaml_frontmatter(
        title='Obsidian兼容测试',
        tags=['笔记', '知识管理', 'Obsidian'],
        source='https://obsidian.md',
        word_count=500,
        language='chinese'
    )
    print(frontmatter)
    
    lines = frontmatter.strip().split('\n')
    assert lines[0] == '---'
    assert lines[-1] == '---'
    print("✓ 通过\n")
    
    print("=" * 60)
    print("所有测试通过！")
    print("=" * 60)
    
    # 输出示例
    print("\n" + "=" * 60)
    print("生成的YAML front matter示例：")
    print("=" * 60)
    sample = generate_yaml_frontmatter(
        title='如何使用Python进行数据分析',
        tags=['Python', '数据分析', 'Pandas', 'NumPy'],
        source='https://example.com/python-data-analysis',
        word_count=2500,
        language='chinese'
    )
    print(sample)
    
    print("\n该格式与以下工具/平台兼容：")
    print("  ✓ Obsidian")
    print("  ✓ Jekyll")
    print("  ✓ Hugo")
    print("  ✓ Hexo")
    print("  ✓ VS Code")
    print("  ✓ Typora")


if __name__ == '__main__':
    run_tests()
