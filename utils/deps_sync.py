"""Default ``uv sync`` extras — RAG included unless user removed it in Settings."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from utils.component_state import is_component_removed
from utils.logger import logger

# Extras synced by default in dev/CI unless the user opted out in Settings.
DEFAULT_DEV_EXTRA = "dev"
DEFAULT_COMPONENT_EXTRAS = ("rag",)


def default_sync_extras(*, include_dev: bool = True) -> list[str]:
    extras: list[str] = []
    if include_dev:
        extras.append(DEFAULT_DEV_EXTRA)
    for name in DEFAULT_COMPONENT_EXTRAS:
        if not is_component_removed(name):
            extras.append(name)
    return extras


def uv_sync_argv(*, include_dev: bool = True, project_dir: Path | None = None) -> list[str]:
    cmd = ["uv", "sync"]
    if project_dir is not None:
        cmd.extend(["--directory", str(project_dir)])
    for extra in default_sync_extras(include_dev=include_dev):
        cmd.extend(["--extra", extra])
    return cmd


def recommended_sync_command(*, include_dev: bool = True) -> str:
    return " ".join(uv_sync_argv(include_dev=include_dev))


def run_uv_sync(*, include_dev: bool = True, project_dir: Path | None = None, timeout: int = 600) -> tuple[bool, str]:
    if not shutil.which("uv"):
        return False, "uv not found"
    cmd = uv_sync_argv(include_dev=include_dev, project_dir=project_dir)
    logger.info("[deps_sync] running: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "uv sync timed out"
    except OSError as e:
        return False, str(e)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-800:]
        return False, tail or f"uv sync exited {result.returncode}"
    return True, "ok"
