"""Runtime enforcement of workspace organization rules."""

from __future__ import annotations

from config.constants import TOPIC_SEP
from sidecar.workspace_rules import load_workspace_rules, needs_workspace_rules_setup

_FORBIDDEN_LEAVES = frozenset(
    {
        "其他",
        "杂项",
        "未分类",
        "other",
        "misc",
        "uncategorized",
        "未归类",
    }
)


class WorkspaceRulesValidationError(ValueError):
    """Raised when an operation violates workspace rules."""


class SchemaValidationError(WorkspaceRulesValidationError):
    """Backward-compatible alias."""


def topic_depth(topic: str) -> int:
    parts = [p.strip() for p in (topic or "").split(TOPIC_SEP) if p.strip()]
    return len(parts)


def validate_topic(topic: str, rules: dict | None = None) -> tuple[bool, str]:
    rules = rules or load_workspace_rules()
    t = (topic or "").strip()
    if not t:
        return False, "主题不能为空"
    depth = topic_depth(t)
    max_depth = int(rules.get("max_topic_depth") or 3)
    if depth > max_depth:
        return False, f"主题层级不能超过 {max_depth} 级（当前 {depth} 级）"
    leaf = t.rsplit(TOPIC_SEP, maxsplit=1)[-1].strip().lower()
    if leaf in {x.lower() for x in _FORBIDDEN_LEAVES}:
        return False, "禁止将内容归入「其他/杂项/未分类」类主题"
    return True, ""


def check_rules_ready() -> tuple[bool, str]:
    if needs_workspace_rules_setup():
        return False, "请先在设置 → 整理规则中完成工作区配置"
    return True, ""


def check_schema_ready() -> tuple[bool, str]:
    return check_rules_ready()


def check_wiki_writable(action: str = "") -> tuple[bool, str]:
    ok, msg = check_rules_ready()
    if not ok:
        return False, msg
    if not load_workspace_rules().get("ai_may_edit_wiki", True):
        hint = f"：{action}" if action else ""
        return False, f"工作区规则禁止 AI 修改 wiki{hint}"
    return True, ""


def check_notes_writable(action: str = "") -> tuple[bool, str]:
    ok, msg = check_rules_ready()
    if not ok:
        return False, msg
    if not load_workspace_rules().get("ai_may_edit_notes"):
        hint = f"：{action}" if action else ""
        return False, f"工作区规则禁止 AI 修改 Notes 正文{hint}"
    return True, ""


def require_topic(topic: str) -> tuple[bool, str]:
    ok, msg = check_rules_ready()
    if not ok:
        return False, msg
    return validate_topic(topic)


def allows_wiki_edit(workspace: str | None = None) -> bool:
    return bool(load_workspace_rules(workspace).get("ai_may_edit_wiki", True))
