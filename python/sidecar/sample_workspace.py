"""Bundled sample workspace for first-run onboarding.

The sample notes live under ``python/sidecar/sample_workspace/`` so they are
carried automatically by both the dev tree and the Tauri release bundle
(``bundle.resources`` includes ``../python/**/*``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from utils.logger import logger

SAMPLE_WORKSPACE_NAME = "NoteAI 示例库"


def sample_root() -> Path:
    """Root directory of the bundled sample workspace resources."""
    return Path(__file__).resolve().parent / "sample_workspace"


def sample_note_count() -> int:
    root = sample_root()
    if not root.exists():
        return 0
    return sum(1 for p in root.rglob("*.md") if not any(part.startswith(".") for part in p.parts))


def _default_target() -> Path:
    docs = Path.home() / "Documents"
    base = docs / SAMPLE_WORKSPACE_NAME
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = docs / f"{SAMPLE_WORKSPACE_NAME} ({index})"
        if not candidate.exists():
            return candidate
        index += 1


def create_sample_workspace(target_dir: str = "") -> tuple[bool, str, str]:
    """Copy bundled sample notes into a fresh workspace folder.

    Returns ``(success, message, workspace_path)``. The target directory must
    be empty (or not exist yet); existing non-empty directories are rejected
    so user data is never overwritten.
    """
    src = sample_root()
    if not src.exists() or sample_note_count() == 0:
        return False, "示例库资源缺失，请重新安装应用", ""
    try:
        target = Path(target_dir).expanduser().resolve() if target_dir else _default_target()
        if target.exists() and any(target.iterdir()):
            return False, f"目标目录不为空，已取消: {target}", ""
        target.mkdir(parents=True, exist_ok=True)
        copied = 0
        for item in sorted(src.rglob("*")):
            rel = item.relative_to(src)
            if any(part.startswith(".") for part in rel.parts):
                continue
            dest = target / rel
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                if item.suffix.lower() == ".md":
                    copied += 1
        logger.info(f"[sample_workspace] created at {target} with {copied} notes")
        return True, f"示例库已创建: {target}", str(target)
    except Exception as e:
        logger.warning(f"[sample_workspace] create failed: {e}")
        return False, f"创建示例库失败: {e}", ""
