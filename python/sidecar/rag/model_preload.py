"""Model preloader: warms up RAG embedder and reranker in background on sidecar start."""

import threading

from utils.logger import logger


class ModelWarmupManager:
    """Downloads / loads heavy models in a background thread so the first
    RAG query does not block the user for seconds."""

    _warmup_done = False
    _lock = threading.Lock()

    @classmethod
    def start_preload(cls):
        t = threading.Thread(target=cls._preload_all, daemon=True, name="model-warmup")
        t.start()

    @classmethod
    def _preload_all(cls):
        with cls._lock:
            if cls._warmup_done:
                return
            cls._warmup_done = True

        logger.warning("[preload] Starting model warmup (embedding + reranker)…")

        cls._preload_embedder()
        threading.Thread(target=cls._preload_reranker, daemon=True, name="reranker-warmup").start()

        logger.warning("[preload] Model warmup complete")

    @classmethod
    def _preload_embedder(cls):
        try:
            from sidecar.rag.embedder import get_model

            get_model()
        except Exception as e:
            logger.warning(f"[preload] embedder warmup skipped: {e}\n")

    @classmethod
    def _preload_reranker(cls):
        try:
            from sidecar.rag.retriever import _get_reranker

            _get_reranker()
        except Exception as e:
            logger.warning(f"[preload] reranker warmup skipped: {e}\n")

    @classmethod
    def is_ready(cls) -> bool:
        with cls._lock:
            return cls._warmup_done
