"""Runtime RAG retrieval settings read from AppConfig."""

from __future__ import annotations

from config import config

DEFAULT_TOP_K = 5
DEFAULT_HYDE_THRESHOLD = 0.33
DEFAULT_RERANK_SKIP_SCORE = 0.75
DEFAULT_DENSE_WEIGHT = 0.7
# INT8 量化 ONNX（Xenova/bge-reranker-base，约 280MB），中英都可用；不下载 1GB fp32。
RERANK_MODEL_NAME = "Xenova/bge-reranker-base"
RERANK_MODEL_FILE = "onnx/model_quantized.onnx"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def top_k() -> int:
    try:
        raw = int(getattr(config, "rag_top_k", DEFAULT_TOP_K))
    except (TypeError, ValueError):
        raw = DEFAULT_TOP_K
    return int(_clamp(float(raw), 1.0, 50.0))


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
