"""WIKI.md heading helpers."""

from pathlib import Path

from config import config


def parse_wiki_headings() -> list:
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = Path(workspace) / "WIKI.md"
    if not wiki_path.exists():
        return []
    try:
        text = wiki_path.read_text(encoding="utf-8")
    except Exception:
        return []

    headings = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            headings.append({"level": 2, "name": stripped[3:].strip()})
        elif stripped.startswith("### "):
            headings.append({"level": 3, "name": stripped[4:].strip()})
    return headings
