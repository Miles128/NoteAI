"""Workspace schema.md — conventions for structure, frontmatter, and AI write scope."""

from __future__ import annotations

import re
from pathlib import Path

from config import config
from config.settings import WORKSPACE_APP_FOLDER

SCHEMA_FILENAME = "schema.md"
LEGACY_SCHEMA_FILENAME = "SCHEMA.md"
SCHEMA_VERSION_MARKER = "noteai-schema-version: 2"
SCHEMA_CONFIGURED_MARKER = "noteai-schema-configured"

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "schema.template.md"

# Compact fallback when docs/schema.template.md is missing
_DEFAULT_SCHEMA_FALLBACK = """# NoteAI 工作区 Schema — 四海

> 本工作区知识库宪法。跨工作区个人偏好见项目根 `NoteAI/profile.md`。

## 1. 定位

AI 知识编译器：采集 → 主题整理 → wiki 综述编译 → RAG 问答。侧重 AI 产品、Agent、RAG、大模型应用。中文优先、简洁技术向。

## 2. 目录

| 路径 | 角色 |
|------|------|
| `Notes/` | 源稿 Markdown，按主题文件夹（最多三级） |
| `wiki/` | WIKI.md 索引、`{叶主题}_综述.md`、`log.md` |
| `Raw/` | 原件归档；自动转换扫描跳过此目录 |
| `.noteai/` | RAG、memory、日志、入库状态 |
| `.ai_memory/project_rules.md` | 本库主题细则（补充本 Schema） |

## 3. 主题

- 逻辑：`一级 > 二级 > 三级`；路径：`Notes/一级/二级/三级/标题.md`
- **文件夹是事实来源**；`WIKI.md` 必须与 `Notes/` 一致（应用内操作后重建同步）
- frontmatter `topic` 与文件夹冲突 → **以文件夹为准** 并回写
- 不确定 → `.pending_topics.json`，禁止扔进「其他/杂项/未分类」
- 优先复用已有主题名；新主题 2～8 字，中文

```yaml
---
topic: AI Agent > 记忆系统
tags: [Agent, 记忆, RAG]
title: 文章标题
---
```

- 标签 2～5 个，中文、有区分度；文件名=标题，禁用 `/ \\ : * ? \" < > |`

## 4. 入库

顺序：转换 → 分类 → RAG 索引 → 级联综述（仅触达主题）→ 同步 WIKI。`Raw/` 内文件不重复自动转换。

## 5. 级联与编译

- **只写** `wiki/*_综述.md` 与 WIKI；**只读** 同 topic 的 `Notes/` 笔记作素材，不改平行笔记正文
- 综述引用来源文件名；增量更新保留已有有效内容
- 链接发现默认待确认（`.links.json`）

## 6. AI 可写范围

```yaml
ai_may_edit_wiki: true
ai_may_edit_notes: false
max_topic_depth: 3
```

允许：综述、WIKI、wiki/log、frontmatter topic/tags、RAG 索引。禁止：改 Notes 正文、删笔记、四级主题、`<!-- human-lock -->` 段落。

## 7. 冲突

综述与笔记矛盾 → 综述并列记录并注明来源，不改 Notes。详见 `docs/schema.template.md`。
"""

DEFAULT_SCHEMA = _DEFAULT_SCHEMA_FALLBACK


def _load_bundled_schema_template() -> str:
    if not _TEMPLATE_PATH.exists():
        return _DEFAULT_SCHEMA_FALLBACK
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
