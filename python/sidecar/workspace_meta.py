"""Workspace meta documents (AGENTS/CLAUDE/GEMINI) — merged into project_rules, hidden from notes."""

from __future__ import annotations

from pathlib import Path

from config import config
from config.settings import NOTES_FOLDER
from sidecar.textutils import parse_frontmatter
from utils.logger import logger

WORKSPACE_META_FILENAMES = frozenset({"AGENTS.md", "CLAUDE.md", "GEMINI.md"})


def is_workspace_meta_name(name: str) -> bool:
    return (name or "").strip().upper() in {n.upper() for n in WORKSPACE_META_FILENAMES}


def is_workspace_meta_path(path: str | Path) -> bool:
    return is_workspace_meta_name(Path(path).name)


def _meta_doc_candidates(ws: Path) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for name in WORKSPACE_META_FILENAMES:
        for candidate in (ws / name, ws / NOTES_FOLDER / name):
            key = str(candidate)
            if key in seen or not candidate.is_file():
                continue
            seen.add(key)
            out.append(candidate)
    return out


def _body_without_frontmatter(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    _fm, body = parse_frontmatter(text)
    return body.strip() if body else text.strip()


def merge_meta_docs_into_project_rules(workspace: str | None = None) -> dict:
    """Merge AGENTS/CLAUDE/GEMINI into `.ai_memory/project_rules.md` and remove sources."""
    ws_s = workspace or config.workspace_path
    if not ws_s:
        return {"success": False, "message": "未设置工作区", "merged": 0, "removed": []}

    ws = Path(ws_s)
    rules_path = ws / ".ai_memory" / "project_rules.md"
    existing = ""
    if rules_path.exists():
        try:
            existing = rules_path.read_text(encoding="utf-8").rstrip()
        except OSError:
            existing = ""

    sections: list[str] = []
    removed: list[str] = []
    for path in _meta_doc_candidates(ws):
        body = _body_without_frontmatter(path)
        if not body:
            try:
                path.unlink()
                removed.append(str(path.relative_to(ws)))
            except OSError as e:
                logger.warning(f"[workspace_meta] remove empty {path.name}: {e}")
            continue
        marker = f"<!-- noteai-merged:{path.name} -->"
        if marker in existing or f"## 来自 {path.name}" in existing:
            try:
                path.unlink()
                removed.append(str(path.relative_to(ws)))
            except OSError:
                pass
            continue
        sections.append(f"{marker}\n\n## 来自 {path.name}\n\n{body}")
        try:
            path.unlink()
            removed.append(str(path.relative_to(ws)))
        except OSError as e:
            logger.warning(f"[workspace_meta] remove {path.name}: {e}")

    if not sections and not removed:
        return {"success": True, "merged": 0, "removed": removed}

    merged_block = "\n\n---\n\n".join(sections)
    if existing:
        new_rules = existing + "\n\n---\n\n" + merged_block
    else:
        new_rules = merged_block
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(new_rules + "\n", encoding="utf-8")
    logger.info(f"[workspace_meta] merged {len(sections)} meta doc(s), removed {len(removed)} file(s)")
    return {"success": True, "merged": len(sections), "removed": removed, "path": str(rules_path)}


def is_inbox_orphan_path(path: str | Path, workspace: str | None = None) -> bool:
    """True for workspace-root or Notes/ root markdown without folder-derived topic."""
    ws_s = workspace or config.workspace_path
    if not ws_s:
        return False
    ws = Path(ws_s)
    p = Path(path)
    try:
        rel = p.resolve().relative_to(ws.resolve())
    except ValueError:
        try:
            rel = p.relative_to(ws)
        except ValueError:
            return False
    parts = rel.parts
    if len(parts) == 1 and parts[0].lower().endswith(".md"):
        return not is_workspace_meta_path(p)
    if len(parts) == 2 and parts[0] == NOTES_FOLDER and parts[1].lower().endswith(".md"):
        return not is_workspace_meta_path(p)
    return False
