"""Weekly / topic brief composition for the semantic workbench."""

from __future__ import annotations

from pathlib import Path

_EMPTY_WEEKLY_BRIEF = "## 知识库周报\n\n过去 {days} 天没有语义变化。"

# 面向普通用户的口语化表述：不暴露内部英文键名。
_KIND_LABELS = {
    "added": "新增了知识",
    "updated": "补充/修正了旧内容",
    "invalidated": "存疑或暂时无法确认",
    "removed": "不再收录",
}
_OBJECT_LABELS = {
    "entity": "笔记中提到的人/事物",
    "concept": "概念",
    "document": "笔记",
}


def build_change_digest(counts: list, items: list) -> tuple[str, str]:
    """把 change log 统计与明细拼成 counts_summary / records 两段文本（跳过已下线的 claim 行）。"""
    by_kind: dict[str, int] = {}
    by_object: dict[str, int] = {}
    for c in counts:
        if c["object_kind"] == "claim":
            continue  # 命题层已下线；跳过历史 claim 变更行
        by_kind[c["change_kind"]] = by_kind.get(c["change_kind"], 0) + c["count"]
        by_object[c["object_kind"]] = by_object.get(c["object_kind"], 0) + c["count"]
    counts_summary = (
        "\n".join(
            f"- {_KIND_LABELS.get(kind, kind)}：{n} 条" for kind, n in sorted(by_kind.items(), key=lambda kv: -kv[1])
        )
        + "\n"
        + "\n".join(
            f"- {_OBJECT_LABELS.get(kind, kind)}：{n} 条"
            for kind, n in sorted(by_object.items(), key=lambda kv: -kv[1])
        )
    )
    records = "\n".join(
        f"- [{c['created_at'][:10]}] {_KIND_LABELS.get(c['change_kind'], c['change_kind'])}"
        f"（{_OBJECT_LABELS.get(c['object_kind'], c['object_kind'])}）: {c['label'] or c['object_id']}"
        + (f"（来源：{Path(c['source_path']).name}）" if c.get("source_path") else "")
        for c in items
        if c["object_kind"] != "claim"
    )
    return counts_summary, records


def empty_weekly_brief(days: int) -> str:
    return _EMPTY_WEEKLY_BRIEF.format(days=days)


def build_topic_change_records(changes: list) -> str:
    return "\n".join(
        f"- [{c['created_at'][:10]}] {c['change_kind']} · {c['object_kind']}: {c['label'] or c['object_id']}"
        + (f"（来源：{Path(c['source_path']).name}）" if c.get("source_path") else "")
        for c in changes
    )


def _compose_weekly_brief(days: int, counts_summary: str, records: str, prompt_template: str) -> tuple[str, bool]:
    """LLM-generated weekly brief when available; structured fallback otherwise."""
    from utils.llm_utils import call_llm_raw

    try:
        prompt = prompt_template.format(days=days, counts_summary=counts_summary, change_records=records)
        text = call_llm_raw(prompt, temperature=0.3)
    except Exception:
        text = ""
    if not text or not text.strip():
        fallback = (
            f"## 知识库周报\n\n"
            f"（未配置 LLM 或生成失败，以下为结构化变化记录）\n\n"
            f"## 统计概览\n\n{counts_summary}\n\n"
            f"## 变化记录\n\n{records}\n"
        )
        return fallback, True
    return text.strip(), False


def _compose_topic_brief(topic: str, days: int, records: str) -> tuple[str, bool]:
    """LLM-generated brief when available; structured fallback otherwise."""
    from prompts import TOPIC_BRIEF_PROMPT
    from utils.llm_utils import call_llm_raw

    try:
        prompt = TOPIC_BRIEF_PROMPT.format(topic_name=topic, days=days, change_records=records)
        text = call_llm_raw(prompt, temperature=0.3)
    except Exception:
        text = ""
    if not text or not text.strip():
        fallback = (
            f"## 主题简报：{topic}\n\n"
            f"（未配置 LLM 或生成失败，以下为结构化变化记录）\n\n"
            f"过去 {days} 天变化：\n\n{records}\n"
        )
        return fallback, True
    return text.strip(), False
