"""Weekly / topic brief composition for the semantic workbench."""

from __future__ import annotations


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
