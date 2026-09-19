"""主题文件夹的文件系统操作（重命名/合并/删除）。

从 sidecar/handlers/topics_handler.py 的 _rename_topic/_delete_topic 下沉。
只做纯文件系统操作，返回移动统计；WIKI 同步与综述级联由 handler 编排。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from config import config
from utils.logger import logger
from utils.topic.paths import topic_artifact_dir, topic_notes_dir


def _move_merge_conflict_free(src: Path, dst_dir: Path) -> Path:
    """移动 src 到 dst_dir，重名时追加 _1/_2 序号。返回最终路径。"""
    dst = dst_dir / src.name
    if dst.exists():
        stem = src.stem
        suffix = src.suffix
        counter = 1
        while dst.exists():
            dst = dst_dir / f"{stem}_{counter}{suffix}"
            counter += 1
    shutil.move(str(src), str(dst))
    return dst


def rename_topic_folder(
    workspace_path: Path,
    old_name: str,
    new_name: str,
) -> dict:
    """把旧主题文件夹改名为新主题；目标已存在时合并内容。

    返回 {"merged": bool}；异常向上抛出由 handler 统一转错误响应。
    """
    old_notes_dir = topic_notes_dir(workspace_path, old_name)
    new_notes_dir = topic_notes_dir(workspace_path, new_name)
    if not old_notes_dir.exists():
        raise FileNotFoundError(f"主题文件夹不存在: {old_name}")

    new_notes_dir.parent.mkdir(parents=True, exist_ok=True)
    merged = False
    if new_notes_dir.exists():
        merged = True
        for item in old_notes_dir.iterdir():
            _move_merge_conflict_free(item, new_notes_dir)
        shutil.rmtree(str(old_notes_dir))
    else:
        shutil.move(str(old_notes_dir), str(new_notes_dir))

    old_abstract_dir = topic_artifact_dir(workspace_path, config.ABSTRACT_FOLDER, old_name)
    new_abstract_dir = topic_artifact_dir(workspace_path, config.ABSTRACT_FOLDER, new_name)
    if old_abstract_dir.exists() and not new_abstract_dir.exists():
        new_abstract_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_abstract_dir), str(new_abstract_dir))

    return {"merged": merged}


def delete_topic_folder(workspace_path: Path, topic_name: str) -> list[Path]:
    """删除主题文件夹：笔记移至 Notes 根目录（重名冲突加序号），文件夹与综述目录删除。

    返回被移动文件的最终路径列表。
    """
    notes_root = workspace_path / config.NOTES_FOLDER
    notes_topic_dir = topic_notes_dir(workspace_path, topic_name)
    moved_files: list[Path] = []

    if notes_topic_dir.exists() and notes_topic_dir.is_dir():
        for f in sorted(notes_topic_dir.rglob("*.md")):
            try:
                moved_files.append(_move_merge_conflict_free(f, notes_root))
            except Exception as e:
                logger.warning(f"[delete_topic] move failed: {e}\n")
        try:
            shutil.rmtree(str(notes_topic_dir))
        except Exception as e:
            logger.error(f"[delete_topic] rmdir: {e}")

    org_dir = topic_artifact_dir(workspace_path, config.ABSTRACT_FOLDER, topic_name)
    if org_dir.exists():
        try:
            shutil.rmtree(str(org_dir))
        except Exception as e:
            logger.error(f"[delete_topic] rmdir org: {e}")

    return moved_files
