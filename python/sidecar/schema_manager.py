"""Workspace schema.md — conventions for structure, frontmatter, and AI write scope."""

from __future__ import annotations

import re
from pathlib import Path

from config import config
from config.constants import TOPIC_SEP
from prompts import SCHEMA_FALLBACK_PROMPT
from utils.topic_manager import TopicManager

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


def list_l1_topics(workspace: str | None = None) -> list[str]:
    """一级主题 = Notes/ 下的一级文件夹名（事实来源）。"""
    ws = workspace or config.workspace_path
    if not ws:
        return []
    tree = TopicManager.build_tree_from_filesystem(ws)
    return [t["name"] for t in tree]


def resolve_survey_topic(topic: str, survey_at_level: int = 2) -> str:
    """将笔记主题映射到应更新综述的主题键（一级或二级）。"""
    parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
    if not parts:
        return topic
    level = min(max(1, survey_at_level), len(parts), 2)
    return TOPIC_SEP.join(parts[:level])


def parse_schema_rules(text: str | None = None) -> dict:
    """Lightweight parse of schema.md flags for runtime checks."""
    raw = text if text is not None else load_schema_text()
    lower = raw.lower()
    rules = {
        "ai_may_edit_wiki": True,
        "ai_may_edit_notes": False,
        "max_topic_depth": 3,
        "auto_update_survey": True,
        "survey_at_level": 2,
    }
    if re.search(r"ai_may_edit_wiki:\s*false", lower):
        rules["ai_may_edit_wiki"] = False
    if re.search(r"ai_may_edit_notes:\s*true", lower):
        rules["ai_may_edit_notes"] = True
    depth_match = re.search(r"max_topic_depth:\s*(\d+)", lower)
    if depth_match:
        rules["max_topic_depth"] = min(3, max(1, int(depth_match.group(1))))
    if re.search(r"auto_update_survey:\s*false", lower):
        rules["auto_update_survey"] = False
    level_match = re.search(r"survey_at_level:\s*(\d+)", lower)
    if level_match:
        rules["survey_at_level"] = min(2, max(1, int(level_match.group(1))))
    return rules


def get_schema_options(workspace: str | None = None) -> dict:
    rules = parse_schema_rules()
    return {
        "l1_topics": list_l1_topics(workspace),
        "max_topic_depth": rules["max_topic_depth"],
        "auto_update_survey": rules["auto_update_survey"],
        "survey_at_level": rules["survey_at_level"],
    }


def build_project_rules_from_workspace(workspace: str | None = None) -> str:
    l1 = list_l1_topics(workspace)
    lines = [
        "# 项目规则",
        "",
        "一级主题与 `Notes/` 下文件夹保持一致（自动同步）：",
        "",
    ]
    if l1:
        lines.extend(f"- {name}" for name in l1)
    else:
        lines.append("- （尚无一级文件夹；创建后会自动同步）")
    lines.extend(
        [
            "",
            "## 禁止自动归入",
            "- 其他",
            "- 杂项",
            "- 未分类",
            "- 资料",
            "",
            "- 笔记与标签优先使用中文",
        ]
    )
    return "\n".join(lines)


def build_schema_markdown(options: dict | None = None, workspace: str | None = None) -> str:
    opts = options or {}
    rules = parse_schema_rules()
    max_depth = min(3, max(1, int(opts.get("max_topic_depth", rules["max_topic_depth"]))))
    auto_survey = opts.get("auto_update_survey", rules["auto_update_survey"])
    survey_level = min(2, max(1, int(opts.get("survey_at_level", rules["survey_at_level"]))))
    l1 = list_l1_topics(workspace)
    l1_display = "、".join(f"`{t}`" for t in l1) if l1 else "（随 `Notes/` 一级文件夹自动同步）"
    depth_path = "一级" + ("/二级" if max_depth >= 2 else "") + ("/三级" if max_depth >= 3 else "")
    survey_level_label = "一级主题" if survey_level == 1 else "二级主题"
    lines = [
        "# NoteAI 工作区 Schema",
        "",
        "> 一级主题由 `Notes/` 文件夹自动决定，与 WIKI 索引保持一致。",
        "",
        "## 1. 目录结构",
        "",
        f"- `Notes/`：源稿 Markdown，按主题文件夹（最多 {max_depth} 级）",
        "- `wiki/`：WIKI.md、`{主题}_综述.md`、`log.md`",
        "- `Raw/`：原件归档",
        "- `.noteai/`：RAG、memory、日志",
        "- `.ai_memory/project_rules.md`：主题细则（L1 自动同步）",
        "",
        "## 2. 主题体系",
        "",
        f"- 分隔符：` > `，最多 {max_depth} 层",
        f"- 路径：`Notes/{depth_path}/标题.md`",
        "- **文件夹为事实来源**；`WIKI.md` 与 `Notes/` 文件夹保持一致",
        f"- 当前一级主题：{l1_display}",
        "- 不确定分类 → `.pending_topics.json`，禁止「其他/杂项/未分类」",
        "",
        "## 3. Frontmatter",
        "",
        "```yaml",
        "---",
        "topic: 一级主题" + (" > 二级主题" if max_depth >= 2 else "") + (" > 三级主题" if max_depth >= 3 else ""),
        "tags: [标签1, 标签2]",
        "title: 文章标题",
        "---",
        "```",
        "",
        "- 标签 2～5 个，中文优先",
        "- 文件名与标题一致，禁用 `/ \\ : * ? \" < > |`",
        "",
        "## 4. 入库与级联",
        "",
        "- 流水线：转换 → 分类 → 索引 → 级联综述 → 同步 WIKI",
        "- 支持 PDF/DOCX 等自动转换；`Raw/` 内原件不重复转换",
        "- **级联只更新** `wiki/*_综述.md`，不改 `Notes/` 平行笔记正文",
        f"- 自动更新综述：{'开启' if auto_survey else '关闭'}",
        f"- 综述粒度：{survey_level_label}（`wiki/{{主题名}}_综述.md`）",
        "",
        "## 5. AI 可写范围",
        "",
        "```yaml",
        "ai_may_edit_wiki: true",
        "ai_may_edit_notes: false",
        f"max_topic_depth: {max_depth}",
        f"auto_update_survey: {'true' if auto_survey else 'false'}",
        f"survey_at_level: {survey_level}",
        "```",
        "",
        f"<!-- {SCHEMA_VERSION_MARKER} -->",
        f"<!-- {SCHEMA_CONFIGURED_MARKER} -->",
    ]
    return "\n".join(lines)


def save_schema_options(options: dict, workspace: str | None = None) -> bool:
    ws = workspace or config.workspace_path
    if not ws:
        return False
    content = finalize_schema_content(build_schema_markdown(options, ws))
    path = Path(ws) / SCHEMA_FILENAME
    path.write_text(content, encoding="utf-8")
    rules_path = Path(ws) / ".ai_memory" / "project_rules.md"
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(build_project_rules_from_workspace(ws), encoding="utf-8")
    return True


def schema_prompt_snippet(max_chars: int = 1500) -> str:
    """Context block for LLM calls (classification, survey)."""
    text = load_schema_text()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…（已截断）"
    rules = parse_schema_rules(text)
    flags = (
        f"ai_may_edit_wiki={rules['ai_may_edit_wiki']}, "
        f"ai_may_edit_notes={rules['ai_may_edit_notes']}, "
        f"max_topic_depth={rules['max_topic_depth']}, "
        f"auto_update_survey={rules['auto_update_survey']}, "
        f"survey_at_level={rules['survey_at_level']}"
    )
    return f"【工作区 SCHEMA 摘要】\n{flags}\n\n{text}"


def allows_wiki_edit(workspace: str | None = None) -> bool:
    text = load_schema_text(workspace)
    return parse_schema_rules(text)["ai_may_edit_wiki"]
