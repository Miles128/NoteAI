import os
import shutil
import threading
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


from utils.logger import logger

_DENSE_MODEL = None
_DENSE_MODEL_LOCK = threading.Lock()

DENSE_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DENSE_DIM = 512

# HF hub 缓存目录名 fastembed：Qdrant/bge-small-zh-v1.5
_FF_MODEL_FOLDER = "models--Qdrant--bge-small-zh-v1.5"

# fastembed is imported lazily inside functions to speed up
# module import time (it is a heavy C extension).


def _onnx_inference_threads() -> int | None:
    n = os.cpu_count()
    if not n:
        return None
    return min(8, max(1, n))


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
    global _DENSE_MODEL
    with _DENSE_MODEL_LOCK:
        _DENSE_MODEL = None


def _get_dense_model(download_callback=None):
    global _DENSE_MODEL
    _ensure_hf_env()
    _ensure_fastembed_cache()
    with _DENSE_MODEL_LOCK:
        if _DENSE_MODEL is not None:
            return _DENSE_MODEL
        for attempt in range(2):
            try:
                if download_callback:
                    download_callback("正在加载 Embedding 模型…" if attempt == 0 else "正在重新下载 Embedding 模型…")
                from fastembed import TextEmbedding

                _dense = TextEmbedding(
                    DENSE_MODEL_NAME,
                    cache_dir=str(_fastembed_cache_root()),
                    threads=_onnx_inference_threads(),
                )
                _DENSE_MODEL = _dense
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
    model = _get_dense_model(download_callback=download_callback)
    prefixed = _bge_prefix(texts, is_query=False)

    embeddings = []
    total = len(prefixed)
    for idx, emb in enumerate(model.embed(prefixed)):
        embeddings.append(emb.tolist())
        if progress_callback and total > 1 and idx % max(1, total // 10) == 0:
            progress_callback(min(idx + 1, total), total, "正在生成 Embedding...")

    dense_vecs = np.array(embeddings)
    if progress_callback and total > 0:
        progress_callback(total, total, "Embedding 生成完成")
    return {"dense_vecs": dense_vecs}


def encode_query(query: str) -> dict:
    if not query:
        return {"dense_vec": None}
    model = _get_dense_model()
    prefixed = _bge_prefix([query], is_query=True)
    embeddings = list(model.embed(prefixed))
    dense = embeddings[0].tolist()
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
