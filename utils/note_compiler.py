"""Rule + LLM note compilation after file conversion (ingest pipeline)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import yaml

from config import config
from config.settings import NOTES_FOLDER
from sidecar.compile_state import file_needs_compile, mark_compiled
from sidecar.textutils import parse_frontmatter
from utils.logger import logger

_CONVERTED_SOURCE_EXTS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".html", ".htm", ".txt"}

_PAGE_NUM_LINE = re.compile(
    r"^\s*(?:第\s*\d+\s*页|Page\s+\d+\s*(?:of\s+\d+)?|\d+\s*/\s*\d+|[-—]\s*\d+\s*[-—])\s*$",
    re.IGNORECASE,
)
_COPYRIGHT_LINE = re.compile(
    r"^\s*(?:版权所有|Copyright|All\s+Rights\s+Reserved|CONFIDENTIAL)\b",
    re.IGNORECASE,
)
_REPEAT_HEADER = re.compile(r"^(?:\.{3,}|_{3,}|-{3,})\s*$")


def _load_project_rules(workspace: str) -> str:
    for rel in (".ai_memory/project_rules.md", "NoteAI/GUIDE.md"):
        path = Path(workspace) / rel
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text[:2000]
            except OSError:
                continue
    return "（无额外规则）"


def rule_clean_markdown(body: str) -> str:
    """Heuristic cleanup before LLM: headers, footers, page numbers."""
    if not body:
        return body

    lines = body.splitlines()
    cleaned: list[str] = []
    prev_blank = False
    seen_short: dict[str, int] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if not prev_blank:
                cleaned.append("")
                prev_blank = True
            continue
        prev_blank = False

        if _PAGE_NUM_LINE.match(stripped):
            continue
        if _COPYRIGHT_LINE.match(stripped):
            continue
        if _REPEAT_HEADER.match(stripped) and len(cleaned) > 3:
            continue

        # Drop lines repeated many times (typical running header/footer)
        key = stripped.lower()[:80]
        if len(stripped) < 60:
            seen_short[key] = seen_short.get(key, 0) + 1
            if seen_short[key] >= 4:
                continue

        cleaned.append(line.rstrip())

    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _source_from_frontmatter(fm: dict | None) -> str:
    if not fm:
        return ""
    source = fm.get("source") or fm.get("origin") or ""
    return str(source).strip()


def should_compile_file(full: Path, fm: dict | None, *, force: bool = False) -> bool:
    if force:
        return True
    source = _source_from_frontmatter(fm)
    if source:
        ext = Path(source).suffix.lower()
        if ext in _CONVERTED_SOURCE_EXTS:
            return True
    return False


def _should_compile_file(full: Path, fm: dict | None, *, force: bool = False) -> bool:
    return should_compile_file(full, fm, force=force)


def scan_compile_pending(workspace: str) -> list[str]:
    """Notes from PDF/Word sources that still need compile."""
    ws = Path(workspace)
    out: list[str] = []
    for md in ws.rglob("*.md"):
        if md.name.startswith(".") or "wiki" in md.parts:
            continue
        if NOTES_FOLDER not in md.parts:
            continue
        try:
            raw = md.read_text(encoding="utf-8")
            fm, _ = parse_frontmatter(raw)
        except OSError:
            continue
        if not should_compile_file(md, fm):
            continue
        rel = str(md.relative_to(ws))
        mtime = md.stat().st_mtime
        if file_needs_compile(rel, mtime, workspace):
            out.append(rel)
    return out


def compile_note_file(
    file_path: str,
    *,
    use_llm: bool = True,
    force: bool = False,
) -> dict:
    """Apply rule cleanup + optional LLM compile; preserve frontmatter."""
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "compiled": False}

    ws = Path(workspace)
    full = ws / file_path if not Path(file_path).is_absolute() else Path(file_path)
    if not full.exists() or full.suffix.lower() != ".md":
        return {"success": False, "message": "非 Markdown 文件", "compiled": False}

    rel = str(full.relative_to(ws))
    try:
        raw = full.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(raw)
    except OSError as e:
        return {"success": False, "message": str(e), "compiled": False}

    if not _should_compile_file(full, fm, force=force):
        return {"success": True, "compiled": False, "skipped": True, "file": rel, "message": "无需编译"}

    mtime = full.stat().st_mtime
    if not force and not file_needs_compile(rel, mtime, workspace):
        return {"success": True, "compiled": False, "skipped": True, "file": rel, "message": "已编译且未改动"}

    cleaned = rule_clean_markdown(body)
    if len(cleaned.strip()) < 30:
        return {"success": False, "message": "正文过短", "compiled": False, "file": rel}

    new_body = cleaned
    llm_used = False

    if use_llm:
        try:
            from utils.llm_utils import APIConfigError, call_llm_raw, check_api_config

            ok, msg = check_api_config()
            if ok:
                from prompts.note_compile import INGEST_NOTE_COMPILE_PROMPT

                rules = _load_project_rules(workspace)
                prompt = INGEST_NOTE_COMPILE_PROMPT.format(
                    project_rules=rules,
                    content=cleaned[:12000],
                )
                rewritten = call_llm_raw(prompt, temperature=0.25)
                if rewritten and len(rewritten.strip()) > len(cleaned.strip()) * 0.4:
                    new_body = rewritten.strip()
                    llm_used = True
            else:
                logger.warning(f"[note_compiler] LLM skipped: {msg}")
        except APIConfigError as e:
            logger.warning(f"[note_compiler] LLM skipped: {e}")
        except Exception as e:
            logger.warning(f"[note_compiler] LLM compile failed, keeping rule-cleaned body: {e}")

    if fm is not None:
        fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
        output = f"---\n{fm_str}\n---\n\n{new_body}\n"
    else:
        output = f"{new_body}\n"

    full.write_text(output, encoding="utf-8")
    mark_compiled(rel, full.stat().st_mtime, workspace)

    return {
        "success": True,
        "compiled": True,
        "file": rel,
        "llm": llm_used,
        "message": "笔记已编译" + ("（含 LLM）" if llm_used else "（规则清理）"),
    }


def compile_notes_batch(
    rel_paths: list[str],
    *,
    progress_cb: Callable[[int, int, str], None] | None = None,
    use_llm: bool = True,
    force: bool = False,
) -> tuple[int, list[str]]:
    """Compile a batch of notes; returns (count, rel_paths actually changed)."""
    changed: list[str] = []
    total = len(rel_paths)
    compiled = 0

    for i, rel in enumerate(rel_paths):
        if progress_cb:
            progress_cb(i + 1, total, f"编译 ({i + 1}/{total}): {Path(rel).name}")
        try:
            result = compile_note_file(rel, use_llm=use_llm, force=force)
            if result.get("compiled"):
                compiled += 1
                changed.append(rel)
        except Exception as e:
            logger.warning(f"[note_compiler] {rel}: {e}")
            continue

    return compiled, changed
