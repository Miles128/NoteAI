import sys
import json
import shutil
import re
from pathlib import Path
from datetime import datetime

from config import config


def _safe_topic_segment(segment: str) -> str:
    safe = "".join(c for c in segment if c.isalnum() or c in ('_', '-', '.', ' ') or '\u4e00' <= c <= '\u9fff').strip()
    if not safe or '..' in safe:
        return ""
    return safe


def _safe_topic_path(topic: str) -> str:
    parts = topic.split('/')
    safe_parts = []
    for p in parts:
        s = _safe_topic_segment(p)
        if not s:
            return ""
        safe_parts.append(s)
    return '/'.join(safe_parts)


def get_organized_topic_dir(topic: str) -> Path | None:
    workspace = config.workspace_path
    if not workspace:
        return None
    safe = _safe_topic_path(topic)
    if not safe:
        return None
    return Path(workspace) / config.ORGANIZED_FOLDER / safe


def get_survey_path(topic: str) -> Path | None:
    topic_dir = get_organized_topic_dir(topic)
    if not topic_dir:
        return None
    leaf_name = _safe_topic_segment(topic.split('/')[-1])
    return topic_dir / f"{leaf_name}_综述.md"


def ensure_topic_folder(topic: str) -> dict:
    safe_topic = _safe_topic_path(topic)
    if not safe_topic:
        return {"success": False, "message": "主题名称非法"}

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    notes_dir = Path(workspace) / config.NOTES_FOLDER / safe_topic
    organized_dir = Path(workspace) / config.ORGANIZED_FOLDER / safe_topic

    is_new = not notes_dir.exists() and not organized_dir.exists()

    notes_dir.mkdir(parents=True, exist_ok=True)
    organized_dir.mkdir(parents=True, exist_ok=True)

    if is_new:
        append_changelog(f"创建主题文件夹: Notes/{safe_topic}/, {config.ORGANIZED_FOLDER}/{safe_topic}/")

    return {"success": True, "topic_dir": str(notes_dir), "organized_dir": str(organized_dir), "is_new": is_new}


def move_file_to_topic_folder(file_path: str, topic: str) -> dict:
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    src = Path(file_path)
    if not src.exists():
        src = Path(workspace) / file_path
    if not src.exists():
        return {"success": False, "message": f"文件不存在: {file_path}"}

    safe_topic = _safe_topic_path(topic)
    if not safe_topic:
        return {"success": False, "message": "主题名称非法"}

    topic_dir = Path(workspace) / config.NOTES_FOLDER / safe_topic
    topic_dir.mkdir(parents=True, exist_ok=True)

    dst = topic_dir / src.name
    if dst.exists() and dst.resolve() != src.resolve():
        stem = src.stem
        suffix = src.suffix
        counter = 1
        while dst.exists():
            dst = topic_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    if dst.resolve() == src.resolve():
        return {"success": True, "message": "文件已在目标位置", "new_path": str(dst.relative_to(workspace))}

    try:
        shutil.move(str(src), str(dst))
        new_rel = str(dst.relative_to(workspace))
        append_changelog(f"文件归类: {src.name} → Notes/{safe_topic}/")
        return {"success": True, "message": f"已移动到 {new_rel}", "new_path": new_rel}
    except Exception as e:
        return {"success": False, "message": f"文件操作失败: {e}"}


def collect_topic_notes(topic: str, max_chars: int = 2000) -> list[dict]:
    workspace = config.workspace_path
    if not workspace:
        return []

    workspace_path = Path(workspace)
    notes = []

    for md_file in sorted(workspace_path.rglob('*.md')):
        if md_file.name.startswith('.'):
            continue
        if md_file.name.lower() in ('wiki.md', 'tags.md'):
            continue
        if md_file.name.endswith('_综述.md'):
            continue
        try:
            text = md_file.read_text(encoding='utf-8')
            from sidecar.textutils import parse_frontmatter
            fm, body = parse_frontmatter(text)

            topic_match = False
            if fm:
                file_topic = fm.get('topic', '')
                if isinstance(file_topic, str) and file_topic == topic:
                    topic_match = True
                file_topics = fm.get('topics', [])
                if isinstance(file_topics, list) and topic in file_topics:
                    topic_match = True

            if topic_match:
                content = body.strip()[:max_chars]
                if content:
                    notes.append({
                        "file_name": md_file.name,
                        "file_path": str(md_file.relative_to(workspace_path)),
                        "content": content,
                    })
        except Exception:
            continue

    return notes


def generate_new_survey(topic: str, notes: list[dict], on_chunk=None) -> dict:
    from prompts.cascade import CASCADE_SURVEY_NEW_PROMPT
    from utils.llm_utils import create_llm, check_api_config, APIConfigError

    try:
        is_valid, error_msg = check_api_config()
        if not is_valid:
            return {"success": False, "message": error_msg}
    except APIConfigError as e:
        return {"success": False, "message": str(e)}

    notes_content = '\n\n---\n\n'.join(
        f"### {n['file_name']}\n\n{n['content']}" for n in notes
    )

    prompt = CASCADE_SURVEY_NEW_PROMPT.format(
        topic_name=topic,
        notes_content=notes_content
    )

    full_text = ""
    try:
        from langchain_core.prompts import PromptTemplate
        llm = create_llm(temperature=0.3)
        pt = PromptTemplate(template=prompt, input_variables=[])
        chain = pt | llm

        for chunk in chain.stream({}):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_text += token
            if on_chunk:
                on_chunk(token)

        survey_path = get_survey_path(topic)
        if not survey_path:
            return {"success": False, "message": "主题名称非法"}

        survey_path.parent.mkdir(parents=True, exist_ok=True)
        survey_path.write_text(full_text.strip(), encoding='utf-8')

        append_changelog(f"生成综述: {config.ORGANIZED_FOLDER}/{_safe_topic_path(topic)}/{survey_path.name}")
        return {"success": True, "survey_path": str(survey_path)}
    except Exception as e:
        return {"success": False, "message": f"综述生成失败: {e}"}


def update_existing_survey(topic: str, new_notes: list[dict], on_chunk=None) -> dict:
    from prompts.cascade import CASCADE_SURVEY_UPDATE_PROMPT
    from utils.llm_utils import create_llm, check_api_config, APIConfigError

    survey_path = get_survey_path(topic)
    if not survey_path or not survey_path.exists():
        return generate_new_survey(topic, new_notes, on_chunk)

    try:
        is_valid, error_msg = check_api_config()
        if not is_valid:
            return {"success": False, "message": error_msg}
    except APIConfigError as e:
        return {"success": False, "message": str(e)}

    existing_text = survey_path.read_text(encoding='utf-8')

    new_notes_content = '\n\n---\n\n'.join(
        f"### {n['file_name']}\n\n{n['content']}" for n in new_notes
    )

    prompt = CASCADE_SURVEY_UPDATE_PROMPT.format(
        topic_name=topic,
        existing_survey=existing_text,
        new_notes=new_notes_content
    )

    full_text = ""
    try:
        from langchain_core.prompts import PromptTemplate
        llm = create_llm(temperature=0.3)
        pt = PromptTemplate(template=prompt, input_variables=[])
        chain = pt | llm

        for chunk in chain.stream({}):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_text += token
            if on_chunk:
                on_chunk(token)

        survey_path.write_text(full_text.strip(), encoding='utf-8')

        append_changelog(f"更新综述: {config.ORGANIZED_FOLDER}/{_safe_topic_path(topic)}/{survey_path.name}")
        return {"success": True, "survey_path": str(survey_path)}
    except Exception as e:
        return {"success": False, "message": f"综述更新失败: {e}"}


def cascade_on_topic_resolved(file_path: str, topic: str, on_chunk=None) -> dict:
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    folder_result = ensure_topic_folder(topic)
    if not folder_result["success"]:
        return folder_result

    is_new_topic = folder_result.get("is_new", False)

    move_result = move_file_to_topic_folder(file_path, topic)

    notes = collect_topic_notes(topic)

    survey_path = get_survey_path(topic)
    survey_exists = survey_path and survey_path.exists()

    survey_result = None
    if is_new_topic or not survey_exists:
        if notes:
            survey_result = generate_new_survey(topic, notes, on_chunk)
        else:
            append_changelog(f"主题「{topic}」暂无笔记，跳过综述生成")
    else:
        new_file_name = Path(file_path).name if Path(file_path).exists() else file_path
        new_file_notes = [n for n in notes if n["file_name"] == new_file_name]
        if not new_file_notes and notes:
            new_file_notes = [notes[-1]]
        if new_file_notes:
            survey_result = update_existing_survey(topic, new_file_notes, on_chunk)

    return {
        "success": True,
        "is_new_topic": is_new_topic,
        "move_result": move_result,
        "survey_result": survey_result,
        "notes_count": len(notes),
    }


def append_changelog(message: str):
    workspace = config.workspace_path
    if not workspace:
        return

    log_path = Path(workspace) / "wiki" / "log.md"

    if not log_path.parent.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if not log_path.exists():
        header = "# 知识库变更日志\n\n"
        log_path.write_text(header, encoding='utf-8')

    try:
        content = log_path.read_text(encoding='utf-8')
    except Exception:
        content = ""

    today = datetime.now().strftime('%Y-%m-%d')
    day_header = f"\n## {today}\n"

    if day_header.strip() not in content:
        if not content.endswith('\n'):
            content += '\n'
        content += day_header

    entry = f"- `{timestamp}` {message}\n"

    lines = content.split('\n')
    insert_idx = len(lines)
    for i, line in enumerate(lines):
        if line.strip() == day_header.strip():
            insert_idx = i + 1
            break

    lines.insert(insert_idx, entry.rstrip('\n'))
    log_path.write_text('\n'.join(lines), encoding='utf-8')


def get_changelog(limit: int = 50) -> list[dict]:
    workspace = config.workspace_path
    if not workspace:
        return []

    log_path = Path(workspace) / "wiki" / "log.md"
    if not log_path.exists():
        return []

    try:
        content = log_path.read_text(encoding='utf-8')
    except Exception:
        return []

    entries = []
    for line in content.split('\n'):
        m = re.match(r'^-\s+`(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})`\s+(.+)$', line.strip())
        if m:
            entries.append({
                "timestamp": m.group(1),
                "message": m.group(2),
            })

    return entries[-limit:]


def check_and_generate_surveys(on_progress=None) -> dict:
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    from utils.topic_assigner import parse_wiki_headings

    headings = parse_wiki_headings()
    if not headings:
        return {"success": True, "checked": 0, "generated": 0, "skipped": 0, "message": "没有找到任何主题"}

    total = len(headings)
    generated = 0
    skipped = 0
    errors = []

    for i, h in enumerate(headings):
        topic = h["name"]
        if on_progress:
            on_progress(i, total, f"检查主题「{topic}」...")

        survey_path = get_survey_path(topic)
        if survey_path and survey_path.exists():
            skipped += 1
            continue

        notes = collect_topic_notes(topic)
        if not notes:
            skipped += 1
            append_changelog(f"主题「{topic}」暂无笔记，跳过综述生成")
            continue

        ensure_topic_folder(topic)

        if on_progress:
            on_progress(i, total, f"正在为「{topic}」生成综述...")

        result = generate_new_survey(topic, notes)
        if result.get("success"):
            generated += 1
            append_changelog(f"补生成综述: {config.ORGANIZED_FOLDER}/{_safe_topic_path(topic)}/{_safe_topic_segment(topic.split('/')[-1])}_综述.md")
        else:
            errors.append({"topic": topic, "error": result.get("message", "未知错误")})

    if on_progress:
        on_progress(total, total, f"完成：检查 {total} 个主题，生成 {generated} 篇综述")

    return {
        "success": True,
        "checked": total,
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
    }
