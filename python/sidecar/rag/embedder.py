import os
import shutil
import threading
import time
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np

_HF_ENV_CONFIGURED = False
_FASTEMBED_CACHE_PATH_CONFIGURED = False


def _ensure_hf_env():
    global _HF_ENV_CONFIGURED
    if _HF_ENV_CONFIGURED:
        return
    from config.constants import SYSTEM_APP_DATA_DIR

    hf_home = SYSTEM_APP_DATA_DIR / "hf_hub"
    hf_home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_home))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home))
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    if not os.environ.get("NO_PROXY"):
        os.environ["NO_PROXY"] = "huggingface.co,hf-mirror.com"
    elif "huggingface.co" not in os.environ.get("NO_PROXY", ""):
        os.environ["NO_PROXY"] = os.environ["NO_PROXY"] + ",huggingface.co,hf-mirror.com"
    _HF_ENV_CONFIGURED = True


def _fastembed_cache_root() -> Path:
    from config.constants import SYSTEM_APP_DATA_DIR

    root = SYSTEM_APP_DATA_DIR / "fastembed_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ensure_fastembed_cache():
    global _FASTEMBED_CACHE_PATH_CONFIGURED
    if _FASTEMBED_CACHE_PATH_CONFIGURED:
        return
    cache = _fastembed_cache_root()
    os.environ["FASTEMBED_CACHE_PATH"] = str(cache)
    _FASTEMBED_CACHE_PATH_CONFIGURED = True
    try:
        from sidecar.storage_usage import purge_stale_fastembed

        purge_stale_fastembed(cache)
    except Exception:
        pass


from sidecar.rag.rag_config import EMBED_IDLE_UNLOAD_SECONDS
from utils.logger import logger

_DENSE_MODEL = None
_DENSE_MODEL_LOCK = threading.Lock()
_DENSE_USE_LOCK = threading.Lock()
_DENSE_IN_FLIGHT = 0
_DENSE_LAST_USED: float = 0.0
_DENSE_IDLE_TIMER: threading.Timer | None = None
_DENSE_IDLE_GENERATION = 0

DENSE_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DENSE_DIM = 512

# HF hub 缓存目录名 fastembed：Qdrant/bge-small-zh-v1.5
_FF_MODEL_FOLDER = "models--Qdrant--bge-small-zh-v1.5"

# fastembed is imported lazily inside functions to speed up
# module import time (it is a heavy C extension).


def _onnx_inference_threads() -> int | None:
    """Cap ONNX threads: AI spikes should not peg every core by default.

    Priority: 设置页 rag_onnx_threads > 环境变量 NOTEAI_ONNX_THREADS > 自动 min(4, cpu)。
    """
    try:
        from config import config

        cfg_threads = int(getattr(config, "rag_onnx_threads", 0) or 0)
    except Exception:
        cfg_threads = 0
    if cfg_threads > 0:
        return max(1, min(32, cfg_threads))
    raw = os.environ.get("NOTEAI_ONNX_THREADS", "").strip()
    if raw:
        try:
            return max(1, min(32, int(raw)))
        except ValueError:
            pass
    n = os.cpu_count() or 1
    return max(1, min(4, n))


def _purge_bge_zh_snapshot(cache_root: Path) -> None:
    doomed = cache_root / _FF_MODEL_FOLDER
    if doomed.is_dir():
        shutil.rmtree(doomed, ignore_errors=True)
        logger.warning(f"[rag/embedder] Removed incomplete embedding cache dir: {doomed}")


def _is_recoverable_embed_load_err(err: BaseException) -> bool:
    s = str(err).lower()
    return any(
        k in s
        for k in (
            "no_suchfile",
            "onnxruntimeerror",
            "failed to load model",
            "doesn't exist",
            "does not exist",
            "no such file",
            "errno 2",
        )
    )


def reset_dense_model() -> None:
    """Drop the cached dense model, mainly for tests or workspace switches."""
    global _DENSE_MODEL, _DENSE_IDLE_GENERATION, _DENSE_IDLE_TIMER
    with _DENSE_MODEL_LOCK:
        _DENSE_MODEL = None
        _DENSE_IDLE_GENERATION += 1
        if _DENSE_IDLE_TIMER is not None:
            _DENSE_IDLE_TIMER.cancel()
            _DENSE_IDLE_TIMER = None


def _touch_dense_usage_locked() -> None:
    global _DENSE_LAST_USED
    with _DENSE_USE_LOCK:
        _DENSE_LAST_USED = time.monotonic()


def _begin_dense_use() -> None:
    global _DENSE_IN_FLIGHT, _DENSE_LAST_USED
    with _DENSE_USE_LOCK:
        _DENSE_IN_FLIGHT += 1
        _DENSE_LAST_USED = time.monotonic()


def _end_dense_use() -> None:
    global _DENSE_IN_FLIGHT, _DENSE_LAST_USED
    with _DENSE_USE_LOCK:
        _DENSE_IN_FLIGHT = max(0, _DENSE_IN_FLIGHT - 1)
        _DENSE_LAST_USED = time.monotonic()


def _schedule_dense_idle_unload_locked(delay: float | None = None) -> None:
    """Arm the idle-unload timer. Caller must hold ``_DENSE_MODEL_LOCK``."""
    global _DENSE_IDLE_TIMER, _DENSE_IDLE_GENERATION
    wait = EMBED_IDLE_UNLOAD_SECONDS if delay is None else max(0.0, delay)
    _DENSE_IDLE_GENERATION += 1
    generation = _DENSE_IDLE_GENERATION
    if _DENSE_IDLE_TIMER is not None:
        _DENSE_IDLE_TIMER.cancel()
    timer = threading.Timer(wait, _maybe_unload_dense_idle, args=(generation,))
    timer.daemon = True
    _DENSE_IDLE_TIMER = timer
    timer.start()


def _maybe_unload_dense_idle(generation: int) -> None:
    global _DENSE_MODEL, _DENSE_IDLE_TIMER
    reschedule = 0.0
    with _DENSE_MODEL_LOCK:
        if generation != _DENSE_IDLE_GENERATION:
            return
        _DENSE_IDLE_TIMER = None
        if _DENSE_MODEL is None:
            return
        with _DENSE_USE_LOCK:
            busy = _DENSE_IN_FLIGHT
            idle = time.monotonic() - _DENSE_LAST_USED
        if busy > 0:
            reschedule = EMBED_IDLE_UNLOAD_SECONDS
        elif idle < EMBED_IDLE_UNLOAD_SECONDS:
            reschedule = EMBED_IDLE_UNLOAD_SECONDS - idle
        else:
            _DENSE_MODEL = None
    if reschedule > 0:
        with _DENSE_MODEL_LOCK:
            _schedule_dense_idle_unload_locked(reschedule)
        return
    import gc

    gc.collect()
    logger.info(f"[rag/embedder] idle unload after {int(EMBED_IDLE_UNLOAD_SECONDS)}s")


def _create_dense_model(download_callback=None):
    from fastembed import TextEmbedding

    return TextEmbedding(
        DENSE_MODEL_NAME,
        cache_dir=str(_fastembed_cache_root()),
        threads=_onnx_inference_threads(),
    )


def _get_dense_model(download_callback=None):
    global _DENSE_MODEL
    _ensure_hf_env()
    _ensure_fastembed_cache()
    with _DENSE_MODEL_LOCK:
        if _DENSE_MODEL is not None:
            _touch_dense_usage_locked()
            return _DENSE_MODEL
        for attempt in range(2):
            try:
                if download_callback:
                    download_callback("正在加载 Embedding 模型…" if attempt == 0 else "正在重新下载 Embedding 模型…")
                _dense = _create_dense_model(download_callback)
                _DENSE_MODEL = _dense
                _touch_dense_usage_locked()
                _schedule_dense_idle_unload_locked()
                return _DENSE_MODEL
            except Exception as e:
                if attempt == 0 and _is_recoverable_embed_load_err(e):
                    logger.warning(f"[rag/embedder] Load failed ({e!s}); purge cache {_FF_MODEL_FOLDER} and retry.")
                    _purge_bge_zh_snapshot(_fastembed_cache_root())
                    continue
                logger.error(f"[rag/embedder] Failed to load {DENSE_MODEL_NAME}: {e}")
                raise


def _bge_prefix(texts: list[str], is_query: bool = False) -> list[str]:
    if is_query:
        return ["为这个句子生成表示以用于检索相关文章：" + t for t in texts]
    return texts


def get_model(download_callback=None):
    return _get_dense_model(download_callback)


def encode(
    texts: list,
    download_callback=None,
    progress_callback=None,
) -> dict:
    """生成 dense 向量。

    sparse 检索由 bm25s 直接对原始文本建索引，embedder 只负责 dense 向量。
    """
    if not texts:
        return {"dense_vecs": []}
    texts = [t if t and t.strip() else " " for t in texts]
    _begin_dense_use()
    try:
        model = _get_dense_model(download_callback=download_callback)
        prefixed = _bge_prefix(texts, is_query=False)

        embeddings = []
        total = len(prefixed)
        for idx, emb in enumerate(model.embed(prefixed)):
            embeddings.append(emb.tolist())
            if progress_callback and total > 1 and idx % max(1, total // 10) == 0:
                progress_callback(min(idx + 1, total), total, "正在生成 Embedding...")

        dense_vecs = np.array(embeddings)
    finally:
        _end_dense_use()
    if progress_callback and total > 0:
        progress_callback(total, total, "Embedding 生成完成")
    return {"dense_vecs": dense_vecs}


def encode_query(query: str) -> dict:
    if not query:
        return {"dense_vec": None}
    _begin_dense_use()
    try:
        model = _get_dense_model()
        prefixed = _bge_prefix([query], is_query=True)
        embeddings = list(model.embed(prefixed))
        dense = embeddings[0].tolist()
    finally:
        _end_dense_use()
    return {"dense_vec": dense}


def encode_documents(
    texts: list,
    download_callback=None,
    progress_callback=None,
) -> list[dict]:
    if not texts:
        return []
    result = encode(
        texts,
        download_callback=download_callback,
        progress_callback=progress_callback,
    )
    output = []
    for i in range(len(texts)):
        dense = result["dense_vecs"][i].tolist()
        output.append({"dense_vec": dense})
    return output
