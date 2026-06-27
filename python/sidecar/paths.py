"""Resolve user-provided paths against the configured workspace."""

from pathlib import Path

from config import config
from utils.logger import logger


def _has_path_traversal(path: str) -> bool:
    """Check for control characters and traversal sequences that could escape the workspace."""
    if not path:
        return True
    if "\x00" in path or any(ord(ch) < 32 for ch in path):
        return True
    # Reject absolute paths and explicit parent-dir traversal.
    normalized = Path(path).as_posix().replace("\\", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    depth = 0
    for part in parts:
        if part == "..":
            depth -= 1
        else:
            depth += 1
        if depth < 0:
            return True
    return False


def resolve_workspace_path(path: str) -> str | None:
    if not path:
        return None
    workspace = config.workspace_path
    if not workspace:
        logger.warning("resolve_workspace_path: workspace not set")
        return None
    if _has_path_traversal(path):
        logger.warning(f"resolve_workspace_path: path contains traversal or control chars: {path}")
        return None
    try:
        workspace_abs = Path(workspace).resolve()
        target_abs = Path(path).resolve() if Path(path).is_absolute() else (workspace_abs / path).resolve()
        target_abs.relative_to(workspace_abs)
        return str(target_abs)
    except ValueError:
        logger.warning(
            f"resolve_workspace_path: path outside workspace: path={path}, workspace={workspace}",
        )
        return None
    except Exception as e:
        logger.warning(f"resolve_workspace_path error for '{path}': {e}")
        return None


def find_file_by_name_in_workspace(path: str) -> str | None:
    if not path:
        return None
    workspace = config.workspace_path
    if not workspace:
        return None
    filename = Path(path).name
    if not filename:
        return None
    try:
        workspace_abs = Path(workspace).resolve()
        notes_abs = workspace_abs / "Notes"
        if notes_abs.exists():
            for match in notes_abs.rglob(filename):
                if match.is_file() and match.suffix.lower() == Path(filename).suffix.lower():
                    match_abs = match.resolve()
                    try:
                        match_abs.relative_to(workspace_abs)
                        return str(match_abs)
                    except ValueError:
                        continue
        for match in workspace_abs.rglob(filename):
            if match.is_file() and match.suffix.lower() == Path(filename).suffix.lower():
                match_abs = match.resolve()
                try:
                    match_abs.relative_to(workspace_abs)
                    return str(match_abs)
                except ValueError:
                    continue
    except Exception as e:
        logger.warning(f"find_file_by_name_in_workspace error for '{path}': {e}")
    return None
