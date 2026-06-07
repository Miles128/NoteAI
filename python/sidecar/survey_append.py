"""Append RAG chat insights into an existing topic survey via LLM merge."""

from __future__ import annotations

from pathlib import Path

from config import config
from prompts import SURVEY_CHAT_APPEND_PROMPT
from sidecar.cascade import _add_survey_frontmatter, append_changelog, get_survey_path
from sidecar.schema_validator import check_wiki_writable, require_topic
from sidecar.textutils import parse_frontmatter
from utils.wiki_manager import topic_from_notes_path
from utils.workspace_log import append_log


def _resolve_topic(topic: str, context_file: str, ws: Path) -> str:
    t = (topic or "").strip()
    if t:
        return t
    ctx = (context_file or "").strip()
    if not ctx:
        return ""
    path = Path(ctx)
    if not path.is_absolute():
        path = ws / ctx
    if path.exists():
        derived = topic_from_notes_path(path)
        if derived:
            return derived
    return ""


def append_chat_to_survey(
    question: str,
    answer: str,
    topic: str = "",
    context_file: str = "",
) -> dict:
    from sidecar.archive_wiki import parse_save_suggestion

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    ok, msg = check_wiki_writable("追加对话到主题综述")
    if not ok:
        return {"success": False, "message": msg}

    q = (question or "").strip()
    a, _ = parse_save_suggestion((answer or "").strip())
    if not q or not a:
        return {"success": False, "message": "问题或回答为空"}

    ws = Path(workspace)
    resolved = _resolve_topic(topic, context_file, ws)
    if not resolved:
        return {"success": False, "message": "无法确定主题：请打开一篇已分类笔记，或手动指定 topic"}

    ok, msg = require_topic(resolved)
    if not ok:
        return {"success": False, "message": msg}

    survey_path = get_survey_path(resolved)
    if not survey_path or not survey_path.exists():
        return {
            "success": False,
            "message": f"主题「{resolved}」尚无综述，请先在主题上生成综述，或使用「存到 wiki」",
        }

    try:
        existing_text = survey_path.read_text(encoding="utf-8")
    except OSError as e:
        return {"success": False, "message": f"读取综述失败: {e}"}

    _fm, existing_body = parse_frontmatter(existing_text)
    chat_block = f"### 小忆对话摘录\n\n**问：** {q}\n\n**答：** {a}\n"

    from utils.llm_utils import APIConfigError, check_api_config, create_llm

    try:
        is_valid, error_msg = check_api_config()
        if not is_valid:
            return {"success": False, "message": error_msg}
    except APIConfigError as e:
        return {"success": False, "message": str(e)}

    prompt = SURVEY_CHAT_APPEND_PROMPT.format(
        topic_name=resolved,
        existing_survey=existing_body.strip()[:12000],
        chat_excerpt=chat_block,
    )

    try:
        from langchain_core.prompts import PromptTemplate

        llm = create_llm(temperature=0.3)
        pt = PromptTemplate(template=prompt, input_variables=[])
        chain = pt | llm
        result = chain.invoke({})
        full_text = result.content if hasattr(result, "content") else str(result)
        merged = full_text.strip()
        if not merged:
            return {"success": False, "message": "LLM 未返回有效内容"}
    except Exception as e:
        return {"success": False, "message": f"综述合并失败: {e}"}

    survey_path.write_text(_add_survey_frontmatter(resolved, merged), encoding="utf-8")
    rel = str(survey_path.relative_to(ws))
    append_changelog(f"小忆对话追加到综述: {resolved}")
    append_log("survey", f"对话追加到综述: {resolved}", rel)

    return {
        "success": True,
        "path": rel,
        "topic": resolved,
        "message": f"已追加到主题综述「{resolved}」",
    }
