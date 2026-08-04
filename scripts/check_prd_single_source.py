"""Fail CI if NoteAI regains a second active PRD."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL_PRD = ROOT / "documents" / "PRD.md"
ARCHIVE_DIR = ROOT / "docs" / "archive"


def main() -> int:
    errors: list[str] = []
    if not CANONICAL_PRD.is_file():
        errors.append("Missing canonical PRD: documents/PRD.md")
    for path in ROOT.rglob("PRD.md"):
        if path == CANONICAL_PRD or path.is_relative_to(ARCHIVE_DIR):
            continue
        errors.append(f"Active duplicate PRD found: {path.relative_to(ROOT)}; archive it under docs/archive/")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
