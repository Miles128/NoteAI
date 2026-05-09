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
