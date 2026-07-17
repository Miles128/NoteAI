#!/usr/bin/env python3
"""Compile every Notes Markdown file into the semantic IR store."""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

from config import config  # noqa: E402
from sidecar.semantic.compiler import compile_semantic_batch  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--claims-only",
        action="store_true",
        help="只重新编译 Claim/Evidence，不改动 Concept/Entity",
    )
    args = parser.parse_args()
    workspace = Path(config.workspace_path or "").expanduser()
    notes = workspace / "Notes"
    if not workspace.is_dir() or not notes.is_dir():
        print("未设置有效工作区或 Notes 目录不存在", file=sys.stderr)
        return 2
    paths = sorted(
        path
        for path in notes.rglob("*.md")
        if not path.name.startswith(".")
        and not path.name.endswith("_综述.md")
        and not any(part.startswith(".") for part in path.relative_to(notes).parts)
    )
    mode = "claims-only" if args.claims_only else "full"
    print(
        f"SEMANTIC_COMPILE_START workspace={workspace} documents={len(paths)} mode={mode}",
        flush=True,
    )

    def progress(current: int, total: int, message: str) -> None:
        print(f"SEMANTIC_COMPILE_PROGRESS {current}/{total} {message}", flush=True)

    stats = compile_semantic_batch(
        workspace, paths, progress_cb=progress, claims_only=args.claims_only
    )
    print("SEMANTIC_COMPILE_RESULT " + json.dumps(stats, ensure_ascii=False, default=list), flush=True)
    return 0 if not stats["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
