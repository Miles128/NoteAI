"""Resolve user-provided paths against the configured workspace."""

import sys
from pathlib import Path

from config import config


def resolve_workspace_path(path: str) -> str | None:
    if not path:
        return None
    workspace = config.workspace_path
    if not workspace:
        print("[WARN] resolve_workspace_path: workspace not set", file=sys.stderr)
        return None
    try:
        workspace_abs = Path(workspace).resolve()
        if Path(path).is_absolute():
            target_abs = Path(path).resolve()
        else:
            target_abs = (workspace_abs / path).resolve()
        target_abs.relative_to(workspace_abs)
        return str(target_abs)
    except ValueError:
        print(
            f"[WARN] resolve_workspace_path: path outside workspace: path={path}, workspace={workspace}",
            file=sys.stderr,
        )
        return None
    except Exception as e:
        print(f"[WARN] resolve_workspace_path error for '{path}': {e}", file=sys.stderr)
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
        for match in workspace_abs.rglob(filename):
            if match.is_file() and match.suffix.lower() == Path(filename).suffix.lower():
                match_abs = match.resolve()
                try:
                    match_abs.relative_to(workspace_abs)
                    return str(match_abs)
                except ValueError:
                    continue
    except Exception:
        pass
    return None
