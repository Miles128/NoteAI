"""WIKI.md heading helpers."""

from pathlib import Path

from config import config


def _resolve_wiki_path(workspace: str) -> Path:
    ws = Path(workspace)
    new_path = ws / "wiki" / "WIKI.md"
    if new_path.exists():
        return new_path
    old_path = ws / "WIKI.md"
    if old_path.exists():
        return old_path
    return new_path


def parse_wiki_headings() -> list:
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = _resolve_wiki_path(workspace)
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
