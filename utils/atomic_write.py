"""Atomic file writes shared by note-writing paths.

Pattern (same as config/workspace_state.py and utils/keyring_store.py):
mkstemp in the target directory -> write -> fsync -> os.replace ->
cleanup temp file on failure. os.replace within one directory is atomic
on POSIX, so a crash can never leave a half-written user note.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(
    path: str | Path,
    text: str,
    encoding: str = "utf-8",
    *,
    mode: int | None = None,
    mkdir_parents: bool = False,
) -> Path:
    """Write text to *path* atomically. Returns the resolved target path.

    Raises OSError on failure (callers convert to user-facing errors).
    """
    target = Path(path)
    if mkdir_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, target)
        return target
    except BaseException:
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except OSError:
            pass
        raise
