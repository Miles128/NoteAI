"""Shared frontmatter / text helpers for sidecar handlers."""

import re

import yaml


def parse_frontmatter(text: str):
    m = re.match(r"^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---", text.lstrip("\ufeff"))
    if not m:
        return None, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    body_start = m.end()
    body = text.lstrip("\ufeff")[body_start:]
    return meta, body


def write_frontmatter(meta: dict | None, body: str, *, had_bom: bool = False) -> str:
    """Reconstruct file content from frontmatter dict and body text.

    If *meta* is ``None`` or empty, returns just the body (no frontmatter block).
    Otherwise returns ``---\\n<yaml>\\n---\\n<body>``.
    """
    prefix = "\ufeff" if had_bom else ""
    if not meta:
        return prefix + body
    fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
    return prefix + "---\n" + fm + "\n---\n" + body.lstrip("\n")
