#!/usr/bin/env python3
"""NoteAI Python sidecar entrypoint (Tauri loads python/main.py)."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "python"))

from sidecar.server import main

if __name__ == "__main__":
    main()
