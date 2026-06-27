"""On-demand Python package manager for optional dependencies.

Provides:
- Isolated application-level venv under SYSTEM_APP_DATA_DIR
- Wheel cache for offline reinstallation
- Version locking via requirements file
- Feature flags for optional dependency groups (rag, cloud, cloud_providers)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from functools import lru_cache

from config.settings import SYSTEM_APP_DATA_DIR
from utils.logger import logger

_APP_VENV_DIR = SYSTEM_APP_DATA_DIR / "venv"
_WHEEL_CACHE_DIR = SYSTEM_APP_DATA_DIR / "wheel_cache"
_REQUIREMENTS_LOCK = SYSTEM_APP_DATA_DIR / "requirements-lock.json"
_INSTALL_LOCK = threading.Lock()

_FEATURE_GROUPS: dict[str, list[str]] = {
    "rag": [
        "FlagEmbedding>=1.2.0",
        "bm25s>=0.2.0",
        "zvec>=0.5.0",
        "fastembed>=0.4.0",
    ],
    "cloud_tencent": ["cos-python-sdk-v5"],
    "cloud_baidu": ["bypy"],
    "cloud_onedrive": [],
}

_FEATURE_LABELS: dict[str, dict[str, str]] = {
    "rag": {
        "name_zh": "向量 RAG 检索",
        "name_en": "Vector RAG",
        "desc_zh": "语义检索、BM25 混合搜索与重排模型（fastembed、bm25s、zvec、FlagEmbedding）",
        "desc_en": "Semantic search, BM25 hybrid retrieval, and reranker models",
    },
    "cloud_tencent": {
        "name_zh": "腾讯云 COS",
        "name_en": "Tencent COS",
        "desc_zh": "腾讯云对象存储同步",
        "desc_en": "Tencent Cloud object storage sync",
    },
    "cloud_baidu": {
        "name_zh": "百度网盘",
        "name_en": "Baidu Pan",
        "desc_zh": "百度网盘同步（bypy）",
        "desc_en": "Baidu Pan sync via bypy",
    },
}

_import_map: dict[str, str] = {
    "cos-python-sdk-v5": "qcloud_cos",
    "FlagEmbedding": "FlagEmbedding",
    "bm25s": "bm25s",
    "zvec": "zvec",
    "fastembed": "fastembed",
    "numpy": "numpy",
    "bypy": "bypy",
}


def _app_python() -> str | None:
    """Return path to the isolated app venv Python, or None if not set up."""
    for candidate in [_APP_VENV_DIR / "bin" / "python3", _APP_VENV_DIR / "bin" / "python"]:
        if candidate.exists():
            return str(candidate)
    if sys.platform == "win32":
        win_py = _APP_VENV_DIR / "Scripts" / "python.exe"
        if win_py.exists():
            return str(win_py)
    return None


def _uv_bin() -> str | None:
    uv = shutil.which("uv")
    if uv:
        return uv
    return shutil.which("pip")


def is_feature_available(feature: str) -> bool:
    """Check if all packages for a feature group are importable."""
    deps = _FEATURE_GROUPS.get(feature, [])
    for dep in deps:
        pkg_name = dep.split(">=")[0].split("==")[0].split("[")[0].strip()
        import_name = _import_map.get(pkg_name, pkg_name.replace("-", "_"))
        try:
            __import__(import_name)
        except ImportError:
            return False
    return True


def _feature_package_names(feature: str) -> list[str]:
    deps = _FEATURE_GROUPS.get(feature, [])
    return [dep.split(">=")[0].split("==")[0].split("[")[0].strip() for dep in deps]


def _target_python() -> str:
    return _app_python() or sys.executable


def uninstall_feature(feature: str) -> tuple[bool, str]:
    """Uninstall packages for a feature group from the active Python environment."""
    deps = _FEATURE_GROUPS.get(feature)
    if deps is None:
        return False, f"unknown feature: {feature}"
    if not deps:
        return True, "no packages required"

    pkg_names = _feature_package_names(feature)
    python = _target_python()
    uv = _uv_bin()

    with _INSTALL_LOCK:
        cmd: list[str]
        if uv and "uv" in uv:
            cmd = [uv, "pip", "uninstall", "--python", python, "-y", *pkg_names]
        else:
            cmd = [python, "-m", "pip", "uninstall", "-y", *pkg_names]

        logger.info("[PackageManager] uninstalling feature %s: %s", feature, " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
            )
            if result.returncode != 0:
                logger.warning("[PackageManager] uninstall failed: %s", result.stderr)
                return False, f"uninstall failed: {(result.stderr or result.stdout or '')[:500]}"
        except subprocess.TimeoutExpired:
            return False, "uninstall timed out"
        except FileNotFoundError as e:
            return False, f"package manager not found: {e}"

        try:
            if _REQUIREMENTS_LOCK.exists():
                existing = json.loads(_REQUIREMENTS_LOCK.read_text(encoding="utf-8"))
                existing.pop(feature, None)
                _REQUIREMENTS_LOCK.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("[PackageManager] failed to update lock file: %s", e)

        return True, "uninstalled"


def list_components() -> list[dict]:
    """Return installable components with availability and user opt-out state."""
    from utils.component_state import get_removed_components, is_component_removed

    removed = get_removed_components()
    items: list[dict] = []
    for key, labels in _FEATURE_LABELS.items():
        items.append(
            {
                "id": key,
                "name_zh": labels.get("name_zh", key),
                "name_en": labels.get("name_en", key),
                "desc_zh": labels.get("desc_zh", ""),
                "desc_en": labels.get("desc_en", ""),
                "installed": is_feature_available(key),
                "user_removed": is_component_removed(key),
                "removable": key in _FEATURE_GROUPS and bool(_FEATURE_GROUPS[key]),
            }
        )
    return items


def ensure_feature(feature: str, *, show_progress: bool = False) -> tuple[bool, str]:
    """Ensure all packages for a feature group are installed.

    Installs into the isolated app venv if available, otherwise falls back to
    the current environment. Uses a process-level lock to avoid concurrent installs.
    """
    if is_feature_available(feature):
        return True, "already installed"

    deps = _FEATURE_GROUPS.get(feature)
    if deps is None:
        return False, f"unknown feature: {feature}"

    with _INSTALL_LOCK:
        if is_feature_available(feature):
            return True, "installed by another thread"

        if not deps:
            return True, "no packages required"

        python = _target_python()
        uv = _uv_bin()

        cmd: list[str]
        if uv and "uv" in uv:
            cache_dir = str(_WHEEL_CACHE_DIR)
            cmd = [
                uv,
                "pip",
                "install",
                "--python",
                python,
                "--cache-dir",
                cache_dir,
                *deps,
            ]
        else:
            cmd = [python, "-m", "pip", "install", *deps]

        logger.info("[PackageManager] installing feature %s: %s", feature, " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=not show_progress,
                text=True,
                timeout=300,
                env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
            )
            if result.returncode != 0:
                logger.warning("[PackageManager] install failed: %s", result.stderr)
                return False, f"install failed: {result.stderr[:500]}"
        except subprocess.TimeoutExpired:
            return False, "install timed out"
        except FileNotFoundError as e:
            return False, f"package manager not found: {e}"

        _save_lock_entry(feature, deps)
        return True, "installed"


def _save_lock_entry(feature: str, deps: list[str]) -> None:
    """Persist the installed feature set for offline verification."""
    try:
        _WHEEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        existing = {}
        if _REQUIREMENTS_LOCK.exists():
            try:
                existing = json.loads(_REQUIREMENTS_LOCK.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
        existing[feature] = {"packages": deps}
        _REQUIREMENTS_LOCK.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug("[PackageManager] failed to write lock file: %s", e)


def get_missing_features() -> dict[str, bool]:
    """Return availability status for all known feature groups."""
    return {name: is_feature_available(name) for name in _FEATURE_GROUPS}


@lru_cache(maxsize=1)
def preferred_python() -> str:
    """Return the Python executable preferred for running the sidecar.

    In development this is sys.executable; in bundled mode it's the isolated venv.
    """
    app_py = _app_python()
    return app_py if app_py else sys.executable
