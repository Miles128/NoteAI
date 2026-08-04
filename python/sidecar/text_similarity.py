"""文本相似度公共原语：归一化、shingle、simhash、Jaccard。

供笔记近似重复检测（organization_audit 等）复用；
向量相似度见 sidecar/rag，精确哈希重复见 sidecar/kb_lint。
"""

from __future__ import annotations

import hashlib
import math
import re

SHINGLE_SIZE = 5
MAX_SHINGLES = 4000
MAX_COMPARE_CHARS = 16000


def bounded(text: str, limit: int) -> str:
    """超长文本取首尾各半，控制比较成本。"""
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + text[-half:]


def normalize_body(body: str, max_chars: int = MAX_COMPARE_CHARS) -> str:
    """正文归一化：小写、截断、去标点与空白。"""
    text = bounded(body.casefold(), max_chars)
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def shingles(text: str, size: int = SHINGLE_SIZE, max_count: int = MAX_SHINGLES) -> set[str]:
    """定长字符 shingle 集合，数量受 max_count 约束。"""
    if len(text) < size:
        return set()
    count = len(text) - size + 1
    step = max(1, math.ceil(count / max_count))
    return {text[index : index + size] for index in range(0, count, step)}


def simhash(shingle_set: set[str]) -> int:
    """64 位 SimHash 指纹（blake2b 逐位加权）。"""
    if not shingle_set:
        return 0
    weights = [0] * 64
    for shingle in shingle_set:
        hashed = int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")
        for bit in range(64):
            weights[bit] += 1 if hashed & (1 << bit) else -1
    value = 0
    for bit, weight in enumerate(weights):
        if weight >= 0:
            value |= 1 << bit
    return value


def jaccard(left: set[str], right: set[str]) -> float:
    """集合 Jaccard 相似度；任一为空返回 0。"""
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
