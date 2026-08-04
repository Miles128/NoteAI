import os
import sys
from os import PathLike


def _restrict_file_permissions(filepath: str | PathLike[str]) -> None:
    try:
        os.chmod(filepath, 0o600)
    except Exception as e:
        sys.stderr.write(f"[security] restrict permissions failed: {e}\n")
        sys.stderr.flush()
