#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试标签提取功能"""

import re
import math
from collections import defaultdict

STOPWORDS = {
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


def tokenize(text: str) -> list:
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


def compute_tf(tokens: list) -> dict:
    if not tokens:
        return {}
    freq = defaultdict(int)
    for t in tokens:
        freq[t] += 1
    total = len(tokens)
    return {t: count / total for t, count in freq.items()}


def compute_idf(documents: list) -> dict:
    df = defaultdict(int)
    for tokens in documents:
        unique = set(tokens)
        for t in unique:
            df[t] += 1
    n = len(documents)
    return {t: math.log((n + 1) / (df[t] + 1)) for t in df}


def compute_tfidf(tf: dict, idf: dict) -> dict:
    return {t: tf_val * idf.get(t, 0) for t, tf_val in tf.items()}


def extract_tags_from_text(text: str, idf: dict = None) -> list:
    tokens = tokenize(text)
    print(f"分词结果: {tokens[:20]}...")
    print(f"分词数量: {len(tokens)}")
    
    if not tokens:
        return []
    tf = compute_tf(tokens)
    print(f"TF (前10): {dict(list(tf.items())[:10])}")
    
    if idf is None:
        print("单文档模式: 使用TF排序")
        sorted_terms = sorted(tf.items(), key=lambda x: x[1], reverse=True)
        print(f"排序后的术语: {sorted_terms[:10]}")
        tags = [term for term, score in sorted_terms][:MAX_TAGS]
    else:
        print(f"多文档模式: 使用TF-IDF排序")
        print(f"IDF (前10): {dict(list(idf.items())[:10])}")
        tfidf = compute_tfidf(tf, idf)
        print(f"TF-IDF (前10): {dict(list(tfidf.items())[:10])}")
        sorted_terms = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)
        print(f"排序后的术语: {sorted_terms[:10]}")
        tags = [term for term, score in sorted_terms if score >= MIN_TF_IDF_SCORE][:MAX_TAGS]
    
    print(f"提取的标签: {tags}")
    return tags


chinese_text = '''
人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，
它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。
机器学习（Machine Learning）是人工智能的一个子领域，
深度学习（Deep Learning）又是机器学习的一个子领域。
自然语言处理（NLP）、计算机视觉（CV）是人工智能的重要应用方向。
'''

print("=" * 60)
print("测试中文标签提取")
print("=" * 60)
print(f"原文:\n{chinese_text}")
print("\n" + "-" * 60 + "\n")

tags = extract_tags_from_text(chinese_text)
print(f"\n最终标签: {tags}")
