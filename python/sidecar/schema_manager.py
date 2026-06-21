"""Workspace schema.md — conventions for structure, frontmatter, and AI write scope."""

from __future__ import annotations

import re
from pathlib import Path

from config import config
from prompts import SCHEMA_FALLBACK_PROMPT

SCHEMA_FILENAME = "schema.md"
LEGACY_SCHEMA_FILENAME = "SCHEMA.md"
SCHEMA_VERSION_MARKER = "noteai-schema-version: 2"
SCHEMA_CONFIGURED_MARKER = "noteai-schema-configured"

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "schema.template.md"

DEFAULT_SCHEMA = SCHEMA_FALLBACK_PROMPT


def _load_bundled_schema_template() -> str:
    if not _TEMPLATE_PATH.exists():
        return SCHEMA_FALLBACK_PROMPT
    text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    cleaned: list[str] = []
    skip_intro = False
    for line in lines:
        if line.strip().startswith("复制到工作区根目录"):
            skip_intro = True
            continue
        if skip_intro and line.strip() == "---":
            skip_intro = False
            continue
        if skip_intro:
            continue
        cleaned.append(line)
    body = "\n".join(cleaned).strip()
    if SCHEMA_VERSION_MARKER not in body:
        body += f"\n\n<!-- {SCHEMA_VERSION_MARKER} -->\n"
    return body


def _schema_needs_upgrade(text: str) -> bool:
    if SCHEMA_VERSION_MARKER in text:
        return False
    # Legacy generic template shipped before personalized 四海 version
    if text.startswith("# NoteAI 工作区 Schema\n\n本文件定义本工作区的知识库结构"):
        return True
    if "四海" not in text and "noteai-schema-version" not in text:
        return True
    return False


def schema_path(workspace: str | None = None) -> Path | None:
    ws = workspace or config.workspace_path
    if not ws:
        return None
    return Path(ws) / SCHEMA_FILENAME


def is_schema_configured(text: str) -> bool:
    return SCHEMA_CONFIGURED_MARKER in text


def needs_schema_setup(workspace: str | None = None) -> bool:
    path = schema_path(workspace)
    if not path or not path.exists():
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return True
    if is_schema_configured(text):
        return False
    # 已有完整 schema（升级前自动生成）视为已配置，仅补标记
    if SCHEMA_VERSION_MARKER in text and len(text) > 400:
        path.write_text(finalize_schema_content(text), encoding="utf-8")
        return False
    return True


def finalize_schema_content(content: str) -> str:
    body = content.rstrip()
    if SCHEMA_VERSION_MARKER not in body:
        body += f"\n\n<!-- {SCHEMA_VERSION_MARKER} -->\n"
    if SCHEMA_CONFIGURED_MARKER not in body:
        body += f"<!-- {SCHEMA_CONFIGURED_MARKER} -->\n"
    return body


def ensure_schema(workspace: str | None = None) -> Path | None:
    """Legacy rename only; new workspaces use the setup wizard before writing schema."""
    path = schema_path(workspace)
    if not path:
        return None
    legacy = path.parent / LEGACY_SCHEMA_FILENAME
    if legacy.exists() and not path.exists():
        try:
            legacy.rename(path)
        except OSError:
            pass
    return path


def load_schema_text(workspace: str | None = None) -> str:
    path = schema_path(workspace)
    if not path or not path.exists():
        return _load_bundled_schema_template()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return _load_bundled_schema_template()


def save_schema_text(content: str, workspace: str | None = None) -> bool:
    path = schema_path(workspace)
    if not path:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def parse_schema_rules(text: str | None = None) -> dict:
    """Lightweight parse of schema.md flags for runtime checks."""
    raw = text if text is not None else load_schema_text()
    lower = raw.lower()
    rules = {
        "ai_may_edit_wiki": True,
        "ai_may_edit_notes": False,
        "max_topic_depth": 3,
    }
    if re.search(r"ai_may_edit_wiki:\s*false", lower):
        rules["ai_may_edit_wiki"] = False
    if re.search(r"ai_may_edit_notes:\s*true", lower):
        rules["ai_may_edit_notes"] = True
    depth_match = re.search(r"max_topic_depth:\s*(\d+)", lower)
    if depth_match:
        rules["max_topic_depth"] = min(3, max(1, int(depth_match.group(1))))
    return rules


def schema_prompt_snippet(max_chars: int = 1500) -> str:
    """Context block for LLM calls (classification, survey)."""
    text = load_schema_text()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…（已截断）"
    rules = parse_schema_rules(text)
    flags = (
        f"ai_may_edit_wiki={rules['ai_may_edit_wiki']}, "
        f"ai_may_edit_notes={rules['ai_may_edit_notes']}, "
        f"max_topic_depth={rules['max_topic_depth']}"
    )
    return f"【工作区 SCHEMA 摘要】\n{flags}\n\n{text}"


def allows_wiki_edit(workspace: str | None = None) -> bool:
    text = load_schema_text(workspace)
    return parse_schema_rules(text)["ai_may_edit_wiki"]
