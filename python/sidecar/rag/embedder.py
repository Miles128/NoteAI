import math
import os
import sys
import threading

import numpy as np

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
if not os.environ.get("NO_PROXY"):
    os.environ["NO_PROXY"] = "huggingface.co,hf-mirror.com"
elif "huggingface.co" not in os.environ.get("NO_PROXY", ""):
    os.environ["NO_PROXY"] = os.environ["NO_PROXY"] + ",huggingface.co,hf-mirror.com"

from fastembed import TextEmbedding

_DENSE_MODEL = None
_DENSE_MODEL_LOCK = threading.Lock()

DENSE_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DENSE_DIM = 512

import jieba

jieba.setLogLevel(jieba.logging.INFO)

_STOP_WORDS = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"}


def _get_dense_model(download_callback=None):
    global _DENSE_MODEL
    with _DENSE_MODEL_LOCK:
        if _DENSE_MODEL is not None:
            return _DENSE_MODEL
        try:
            if download_callback:
                download_callback("正在加载 Embedding 模型...")
            _DENSE_MODEL = TextEmbedding(DENSE_MODEL_NAME)
            return _DENSE_MODEL
        except Exception as e:
            sys.stderr.write(f"[rag/embedder] Failed to load {DENSE_MODEL_NAME}: {e}\n")
            sys.stderr.flush()
            raise


def _bge_prefix(texts: list[str], is_query: bool = False) -> list[str]:
    if is_query:
        return ["为这个句子生成表示以用于检索相关文章：" + t for t in texts]
    return texts


def _compute_sparse(texts: list[str]) -> list[dict]:
    results = []
    doc_freq = {}
    tokenized = []

    for text in texts:
        tokens = [w for w in jieba.cut(text) if w.strip() and w not in _STOP_WORDS]
        tokenized.append(tokens)
        seen = set(tokens)
        for t in seen:
            doc_freq[t] = doc_freq.get(t, 0) + 1

    n_docs = len(texts)
    idf = {}
    for t, df in doc_freq.items():
        if n_docs <= 1:
            idf[t] = 1.0
        else:
            idf[t] = max(0.0, math.log((n_docs - df + 0.5) / (df + 0.5)) + 1.0)

    for tokens in tokenized:
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        sparse = {}
        for t, count in tf.items():
            if t in idf:
                weight = (count / len(tokens)) * idf[t] if tokens else 0
                if weight > 0:
                    sparse[t] = weight
        results.append(sparse)

    return results


def get_model(download_callback=None):
    return _get_dense_model(download_callback)


def encode(texts: list, download_callback=None) -> dict:
    if not texts:
        return {"dense_vecs": [], "lexical_weights": []}
    texts = [t if t and t.strip() else " " for t in texts]
    model = _get_dense_model(download_callback=download_callback)
    prefixed = _bge_prefix(texts, is_query=False)
    embeddings = list(model.embed(prefixed))
    dense_vecs = np.array([e.tolist() for e in embeddings])
    sparse_weights = _compute_sparse(texts)
    return {"dense_vecs": dense_vecs, "lexical_weights": sparse_weights}


def encode_query(query: str) -> dict:
    if not query:
        return {"dense_vec": None, "lexical_weights": {}}
    model = _get_dense_model()
    prefixed = _bge_prefix([query], is_query=True)
    embeddings = list(model.embed(prefixed))
    dense = embeddings[0].tolist()
    sparse = _compute_sparse([query])[0]
    return {"dense_vec": dense, "lexical_weights": sparse}


def encode_documents(texts: list, download_callback=None) -> list[dict]:
    if not texts:
        return []
    result = encode(texts, download_callback=download_callback)
    output = []
    for i in range(len(texts)):
        dense = result["dense_vecs"][i].tolist()
        sparse = result["lexical_weights"][i]
        output.append({"dense_vec": dense, "lexical_weights": sparse})
    return output
