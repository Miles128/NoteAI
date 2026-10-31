"""Runtime RAG retrieval settings read from AppConfig."""

from __future__ import annotations

from config import config

DEFAULT_TOP_K = 5
# 召回深度只有这一段真正改变检索候选数：候选数 = top_k * 3，并被夹在 [12, 24]
# （retriever._retrieve），所以 1-3 全等于 12、9 以上全等于 24。
MIN_TOP_K = 4
MAX_TOP_K = 8
DEFAULT_HYDE_THRESHOLD = 0.33
DEFAULT_RERANK_SKIP_SCORE = 0.75
DEFAULT_DENSE_WEIGHT = 0.7
# INT8 量化 ONNX（Xenova/bge-reranker-base，约 280MB），中英都可用；不下载 1GB fp32。
RERANK_MODEL_NAME = "Xenova/bge-reranker-base"
RERANK_MODEL_FILE = "onnx/model_quantized.onnx"
# 精排器（约 500MB 常驻）空闲这么久后卸载，下一次使用再加载。
RERANK_IDLE_UNLOAD_SECONDS = 600
# 向量模型（约 150MB 常驻）同理，按需加载、空闲卸载。
EMBED_IDLE_UNLOAD_SECONDS = 600


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def top_k() -> int:
    try:
        raw = int(getattr(config, "rag_top_k", DEFAULT_TOP_K))
    except (TypeError, ValueError):
        raw = DEFAULT_TOP_K
    return int(_clamp(float(raw), float(MIN_TOP_K), float(MAX_TOP_K)))


def hyde_enabled() -> bool:
    return bool(getattr(config, "rag_hyde_enabled", True))


def hyde_threshold() -> float:
    try:
        raw = float(getattr(config, "rag_hyde_threshold", DEFAULT_HYDE_THRESHOLD))
    except (TypeError, ValueError):
        raw = DEFAULT_HYDE_THRESHOLD
    return _clamp(raw, 0.0, 1.0)


def rerank_enabled() -> bool:
    return bool(getattr(config, "rag_rerank_enabled", True))


def rerank_skip_score() -> float:
    try:
        raw = float(getattr(config, "rag_rerank_skip_score", DEFAULT_RERANK_SKIP_SCORE))
    except (TypeError, ValueError):
        raw = DEFAULT_RERANK_SKIP_SCORE
    return _clamp(raw, 0.0, 1.0)


def hybrid_weights() -> tuple[float, float]:
    try:
        dense = float(getattr(config, "rag_dense_weight", DEFAULT_DENSE_WEIGHT))
    except (TypeError, ValueError):
        dense = DEFAULT_DENSE_WEIGHT
    dense = _clamp(dense, 0.0, 1.0)
    return dense, 1.0 - dense
