"""Model preloader: warms up the RAG embedder on first demand (reranker loads lazily)."""

import threading

from utils.logger import logger


class ModelWarmupManager:
    """Downloads / loads heavy models in a background thread so the first
    RAG query does not block the user for seconds."""

    _preload_started = False
    _preload_done = False
    _lock = threading.Lock()

    @classmethod
    def ensure_preload(cls):
        """幂等：确保后台预热线程已启动（可被启动延迟/首次 RAG 查询触发）。"""
        with cls._lock:
            if cls._preload_started:
                return
            cls._preload_started = True
        t = threading.Thread(target=cls._preload_all, daemon=True, name="model-warmup")
        t.start()

    @classmethod
    def start_preload(cls):
        cls.ensure_preload()

    @classmethod
    def schedule_preload(cls, delay: float = 2.0):
        """延迟启动预热：给启动窗口 RPC 让路，避免模型加载抢占 CPU/内存。"""
        t = threading.Timer(delay, cls.ensure_preload)
        t.daemon = True
        t.start()

    @classmethod
    def _preload_all(cls):
        # 只预热 embedder（首次检索必用）；reranker（约 500MB）延迟到真正精排时加载，
        # 空闲后由 reranker 自己的 idle watcher 卸载。
        logger.warning("[preload] Loading embedding model…")
        cls._preload_embedder()
        with cls._lock:
            cls._preload_done = True
        logger.warning("[preload] Embedding model ready")

    @classmethod
    def _preload_embedder(cls):
        try:
            from sidecar.rag.embedder import get_model

            get_model()
        except Exception as e:
            logger.warning(f"[preload] embedder warmup skipped: {e}\n")

    @classmethod
    def is_ready(cls) -> bool:
        with cls._lock:
            return cls._preload_done
