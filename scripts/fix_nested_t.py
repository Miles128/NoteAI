#!/usr/bin/env python3
"""Collapse window.t(window.t('key')) to window.t('key')."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "webui" / "js"
PAT = re.compile(r"window\.t\(window\.t\('([^']+)'\)\)")


def fix(content: str) -> tuple[str, int]:
    n = 0
    while True:
        new, c = PAT.subn(r"window.t('\1')", content)
        n += c
        if c == 0:
            return new, n
        content = new


def main() -> None:
    total = 0
    for path in sorted(ROOT.glob("*.js")):
        if path.name == "i18n.js":
            continue
        text = path.read_text(encoding="utf-8")
        fixed, n = fix(text)
        if n:
            path.write_text(fixed, encoding="utf-8")
            print(f"  {path.name}: {n}")
            total += n
    print(f"fixed {total} nested calls")


if __name__ == "__main__":
    main()
