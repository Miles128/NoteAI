"""ONNX cross-encoder rerank (fastembed), no FlagEmbedding/torch."""

from __future__ import annotations

import threading
import time
from typing import Any, Iterable

from sidecar.rag.rag_config import (
    RERANK_MODEL_FILE,
    RERANK_MODEL_NAME,
    RERANK_MODEL_SOURCE,
    rerank_enabled,
)
from utils.logger import logger

TextCrossEncoder = None  # filled lazily; tests may patch this name

_RERANKER = None
_RERANKER_DISABLED_UNTIL: float = 0.0
_RERANKER_COOLDOWN_SECONDS = 60
_RERANKER_LOCK = threading.Lock()
_RERANK_BATCH = 64
_CUSTOM_REGISTERED = False


def _onnx_threads() -> int | None:
    from sidecar.rag.embedder import _onnx_inference_threads

    return _onnx_inference_threads()


def _cache_dir() -> str:
    from sidecar.rag.embedder import _ensure_fastembed_cache, _ensure_hf_env, _fastembed_cache_root

    _ensure_hf_env()
    _ensure_fastembed_cache()
    return str(_fastembed_cache_root())


def _ensure_quantized_model(encoder_cls) -> None:
    """Register the 280MB INT8 weights; skip the 1GB fp32 BAAI snapshot."""
    global _CUSTOM_REGISTERED
    if _CUSTOM_REGISTERED or not hasattr(encoder_cls, "add_custom_model"):
        return
    listed = encoder_cls.list_supported_models() if hasattr(encoder_cls, "list_supported_models") else []
    supported = {str(m.get("model", "")).lower() for m in listed}
    if RERANK_MODEL_NAME.lower() not in supported:
        from fastembed.common.model_description import ModelSource

        encoder_cls.add_custom_model(
            model=RERANK_MODEL_NAME,
            sources=ModelSource(hf=RERANK_MODEL_SOURCE),
            model_file=RERANK_MODEL_FILE,
            description="INT8 quantized BGE reranker base",
            license="mit",
            size_in_gb=0.28,
        )
    _CUSTOM_REGISTERED = True


def _load_onnx_reranker():
    encoder_cls = globals().get("TextCrossEncoder")
    if encoder_cls is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder as encoder_cls

    _ensure_quantized_model(encoder_cls)
    return encoder_cls(
        RERANK_MODEL_NAME,
        cache_dir=_cache_dir(),
        threads=_onnx_threads(),
    )


def reset_reranker() -> None:
    """Drop the in-memory reranker so model caches can be deleted safely."""
    global _RERANKER, _RERANKER_DISABLED_UNTIL
    with _RERANKER_LOCK:
        _RERANKER = None
        _RERANKER_DISABLED_UNTIL = 0.0


def get_reranker():
    global _RERANKER, _RERANKER_DISABLED_UNTIL

    if not rerank_enabled():
        return None
    if time.time() < _RERANKER_DISABLED_UNTIL:
        return None
    if _RERANKER is not None:
        return _RERANKER
    with _RERANKER_LOCK:
        if time.time() < _RERANKER_DISABLED_UNTIL:
            return None
        if _RERANKER is not None:
            return _RERANKER
        try:
            _RERANKER = _load_onnx_reranker()
            return _RERANKER
        except Exception as e:
            _RERANKER_DISABLED_UNTIL = time.time() + _RERANKER_COOLDOWN_SECONDS
            logger.warning(
                f"[rag/reranker] unavailable, cooling down for {_RERANKER_COOLDOWN_SECONDS}s: {e}"
            )
            return None


def score_documents(reranker: Any, query: str, documents: Iterable[str]) -> list[float]:
    texts = list(documents)
    if not texts:
        return []
    scores = list(reranker.rerank(query, texts, batch_size=_RERANK_BATCH))
    return [float(s) for s in scores]
