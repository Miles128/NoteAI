#!/usr/bin/env python3
"""Collapse duplicate data-i18n / data-i18n-title attributes on the same tag."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "webui" / "index.html"
ATTRS = ("data-i18n", "data-i18n-title", "data-i18n-placeholder")


def dedupe_line(line: str) -> str:
    for attr in ATTRS:
        pattern = rf'({re.escape(attr)}="[^"]+")(?:\s+\1)+'

        def repl(m: re.Match[str]) -> str:
            return m.group(1)

        line = re.sub(pattern, repl, line)
    return line


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else HTML
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    changed = 0
    out: list[str] = []
    for line in lines:
        fixed = dedupe_line(line)
        if fixed != line:
            changed += 1
        out.append(fixed)
    if changed:
        path.write_text("".join(out), encoding="utf-8")
    print(f"{path.name}: deduped {changed} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
