"""Workspace organization rules — JSON in .noteai/workspace_rules.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

from config import config
from config.constants import TOPIC_SEP
from config.settings import WORKSPACE_APP_FOLDER

RULES_FILENAME = "workspace_rules.json"

DEFAULT_RULES: dict = {
    "max_topic_depth": 3,
    "auto_update_survey": True,
    "survey_at_level": 2,
    "ai_may_edit_wiki": True,
    "ai_may_edit_notes": False,
    "configured": False,
}


def _rules_path(workspace: str | None = None) -> Path | None:
    ws = workspace or config.workspace_path
    if not ws:
        return None
    return Path(ws) / WORKSPACE_APP_FOLDER / RULES_FILENAME


def _migrate_from_schema(workspace: str) -> dict | None:
    """One-time import from legacy schema.md if present."""
    schema_path = Path(workspace) / "schema.md"
    if not schema_path.exists():
        return None
    try:
        text = schema_path.read_text(encoding="utf-8")
    except OSError:
        return None
    lower = text.lower()
    rules = dict(DEFAULT_RULES)
    rules["configured"] = "noteai-schema-configured" in text
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


def load_workspace_rules(workspace: str | None = None) -> dict:
    path = _rules_path(workspace)
    ws = workspace or config.workspace_path
    if path and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged = dict(DEFAULT_RULES)
                merged.update(data)
                return merged
        except (OSError, json.JSONDecodeError):
            pass
    if ws:
        migrated = _migrate_from_schema(ws)
        if migrated:
            save_workspace_rules(migrated, ws)
            return migrated
    return dict(DEFAULT_RULES)


def save_workspace_rules(rules: dict, workspace: str | None = None) -> bool:
    path = _rules_path(workspace)
    if not path:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULT_RULES)
    merged.update(rules)
    merged["max_topic_depth"] = min(3, max(1, int(merged.get("max_topic_depth", 3))))
    merged["survey_at_level"] = min(2, max(1, int(merged.get("survey_at_level", 2))))
    merged["auto_update_survey"] = bool(merged.get("auto_update_survey", True))
    merged["ai_may_edit_wiki"] = bool(merged.get("ai_may_edit_wiki", True))
    merged["ai_may_edit_notes"] = bool(merged.get("ai_may_edit_notes", False))
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def needs_workspace_rules_setup(workspace: str | None = None) -> bool:
    return not load_workspace_rules(workspace).get("configured", False)


def list_topic_headings(workspace: str | None = None) -> list[dict]:
    """Return topic paths from the Notes directory, the canonical hierarchy."""
    ws_value = workspace or config.workspace_path
    if not ws_value:
        return []
    notes_root = Path(ws_value) / config.NOTES_FOLDER
    if not notes_root.exists():
        return []

    headings: list[dict] = []
    for directory in sorted(
        (path for path in notes_root.rglob("*") if path.is_dir()),
        key=lambda path: str(path.relative_to(notes_root)),
    ):
        try:
            parts = directory.relative_to(notes_root).parts
        except ValueError:
            continue
        if not parts or len(parts) > 3 or any(part.startswith(".") for part in parts):
            continue
        headings.append(
            {
                "level": len(parts),
                "name": TOPIC_SEP.join(parts),
                "label": parts[-1],
            }
        )
    return headings


def list_l1_topics(workspace: str | None = None) -> list[str]:
    """一级主题来自 Notes/ 文件夹结构。"""
    topics = [h["label"] for h in list_topic_headings(workspace) if h.get("level") == 1]
    if topics:
        return topics
    ws = workspace or config.workspace_path
    if not ws:
        return []
    from utils.topic_manager import TopicManager

    tree = TopicManager.build_tree_from_filesystem(ws)
    return [t["name"] for t in tree]


def get_workspace_rules_options(workspace: str | None = None) -> dict:
    rules = load_workspace_rules(workspace)
    return {
        "l1_topics": list_l1_topics(workspace),
        "max_topic_depth": rules["max_topic_depth"],
        "auto_update_survey": rules["auto_update_survey"],
        "survey_at_level": rules["survey_at_level"],
        "configured": rules.get("configured", False),
    }


def save_workspace_rules_options(options: dict, workspace: str | None = None) -> bool:
    rules = load_workspace_rules(workspace)
    rules["max_topic_depth"] = options.get("max_topic_depth", rules["max_topic_depth"])
    rules["auto_update_survey"] = options.get("auto_update_survey", rules["auto_update_survey"])
    rules["survey_at_level"] = options.get("survey_at_level", rules["survey_at_level"])
    rules["configured"] = True
    return save_workspace_rules(rules, workspace)


def resolve_survey_topic(topic: str, survey_at_level: int = 2) -> str:
    parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
    if not parts:
        return topic
    level = min(max(1, survey_at_level), len(parts), 2)
    return TOPIC_SEP.join(parts[:level])


def format_wiki_topic_structure_for_llm(max_chars: int = 1200, workspace: str | None = None) -> str:
    """主题结构摘要，供分类 LLM 使用（来源：Notes/ 文件夹）。"""
    headings = list_topic_headings(workspace)

    if not headings:
        l1 = list_l1_topics(workspace)
        if not l1:
            return "【工作区主题结构】\n（尚无主题，请根据文章标题建议新主题路径，使用「 > 」分隔层级）"
        lines = ["【工作区主题结构】", "一级主题（来自文件夹）："]
        lines.extend(f"- {name}" for name in l1)
        text = "\n".join(lines)
        return text[:max_chars] + ("…" if len(text) > max_chars else "")

    by_level: dict[int, list[str]] = {}
    for h in headings:
        lvl = int(h.get("level") or 1)
        by_level.setdefault(lvl, []).append(h["name"])

    lines = ["【工作区主题结构】", "来源：Notes/ 文件夹，分类时请优先选用下列路径：", ""]
    for name in by_level.get(1, []):
        lines.append(f"- {name}")
    for name in by_level.get(2, []):
        lines.append(f"  - {name}")
    for name in by_level.get(3, []):
        lines.append(f"    - {name}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text
