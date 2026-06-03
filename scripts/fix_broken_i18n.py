#!/usr/bin/env python3
"""Revert lines with broken nested window.t() patches back to git HEAD."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS_DIR = ROOT / "webui" / "js"
BAD = re.compile(r"window\.t\('[^']*'\s*\+\s*window\.t\(")


def git_content(path: Path) -> str | None:
    rel = path.relative_to(ROOT).as_posix()
    r = subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if r.returncode != 0:
        return None
    return r.stdout


def main() -> None:
    fixed = 0
    for js_path in sorted(JS_DIR.glob("*.js")):
        if js_path.name == "i18n.js":
            continue
        text = js_path.read_text(encoding="utf-8")
        if not BAD.search(text):
            continue
        orig = git_content(js_path)
        if orig is None:
            print(f"skip (no git): {js_path.name}")
            continue
        orig_lines = orig.splitlines(keepends=True)
        cur_lines = text.splitlines(keepends=True)
        if len(orig_lines) != len(cur_lines):
            print(f"warn line count mismatch: {js_path.name}")
        out = []
        for i, line in enumerate(cur_lines):
            if BAD.search(line):
                out.append(orig_lines[i] if i < len(orig_lines) else line)
                fixed += 1
            else:
                out.append(line)
        js_path.write_text("".join(out), encoding="utf-8")
        print(f"fixed {js_path.name}")
    print(f"reverted {fixed} lines")


if __name__ == "__main__":
    main()
