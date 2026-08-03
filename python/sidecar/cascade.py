import re
import shutil
import threading
from pathlib import Path

from config import config
from config.constants import TOPIC_SEP
from utils.logger import logger
from utils.text_utils import parse_frontmatter

_changelog_lock = threading.Lock()

_NEW_SURVEY_NOTES_MAX_CHARS = 12000
_UPDATE_SURVEY_NOTES_MAX_CHARS = 6000
_EXISTING_SURVEY_MAX_CHARS = 8000


def _safe_topic_segment(segment: str) -> str:
    safe = "".join(c for c in segment if c.isalnum() or c in ("_", "-", ".", " ") or "\u4e00" <= c <= "\u9fff").strip()
    if not safe or ".." in safe:
        return ""
    return safe


def _safe_topic_path(topic: str) -> str:
    """将 > 分隔的主题字符串转为文件系统安全路径（用 / 连接）。"""
    from utils.topic_classifier import _norm_topic

    topic = _norm_topic(topic)
    parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
    safe_parts = []
    for p in parts:
        s = _safe_topic_segment(p)
        if not s:
            return ""
        safe_parts.append(s)
    return "/".join(safe_parts)


def get_organized_topic_dir(topic: str) -> Path | None:
    workspace = config.workspace_path
    if not workspace:
        return None
    safe = _safe_topic_path(topic)
    if not safe:
        return None
    return Path(workspace) / config.ABSTRACT_FOLDER / safe


def get_survey_path(topic: str) -> Path | None:
    if not topic:
        return None
    workspace = config.workspace_path
    if not workspace:
        return None
    leaf_name = _safe_topic_segment(topic.rsplit(TOPIC_SEP, maxsplit=1)[-1])
    return Path(workspace) / config.ABSTRACT_FOLDER / f"{leaf_name}_综述.md"


def ensure_topic_folder(topic: str) -> dict:
    safe_topic = _safe_topic_path(topic)
    if not safe_topic:
        return {"success": False, "message": "主题名称非法"}

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    notes_dir = Path(workspace) / config.NOTES_FOLDER / safe_topic
    wiki_dir = Path(workspace) / config.ABSTRACT_FOLDER

    is_new = not notes_dir.exists()

    notes_dir.mkdir(parents=True, exist_ok=True)
    wiki_dir.mkdir(parents=True, exist_ok=True)

    if is_new:
        append_changelog(f"创建主题文件夹: Notes/{safe_topic}/")

    return {"success": True, "topic_dir": str(notes_dir), "organized_dir": str(wiki_dir), "is_new": is_new}


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


def collect_topic_notes(topic: str) -> list[dict]:
    workspace = config.workspace_path
    if not workspace:
        return []

    workspace_path = Path(workspace)
    notes_dir = workspace_path / config.NOTES_FOLDER
    topic_parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
    notes = []

    for md_file in sorted(workspace_path.rglob("*.md")):
        if md_file.name.startswith("."):
            continue
        if "wiki" in md_file.parts:
            continue
        if md_file.name.endswith("_综述.md") or md_file.name.endswith("综述.md"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)

            topic_match = False
            if fm:
                file_topic = fm.get("topic", "")
                if isinstance(file_topic, str):
                    if file_topic == topic or topic_parts and file_topic.startswith(topic + TOPIC_SEP) or len(topic_parts) == 1 and (
                        file_topic == topic_parts[0]
                        or file_topic.startswith(topic_parts[0] + TOPIC_SEP)
                    ):
                        topic_match = True
                file_topics = fm.get("topics", [])
                if isinstance(file_topics, list) and topic in file_topics:
                    topic_match = True

            if not topic_match and topic_parts and notes_dir.exists():
                try:
                    rel = md_file.relative_to(notes_dir)
                except ValueError:
                    rel = None
                if rel and rel.parts:
                    if rel.parts[0] == topic_parts[0]:
                        if len(topic_parts) == 1:
                            topic_match = True
                        elif len(rel.parts) >= 2 and rel.parts[1] == topic_parts[1]:
                            if len(topic_parts) == 2 or len(rel.parts) >= 3 and rel.parts[2] == topic_parts[2]:
                                topic_match = True

            if topic_match:
                content = body.strip()
                if content:
                    notes.append(
                        {
                            "file_name": md_file.name,
                            "file_path": str(md_file.relative_to(workspace_path)),
                            "content": content,
                        }
                    )
        except Exception:
            continue

    return notes


def _compress_text(content: str, target_ratio: float = 0.6) -> str:
    try:
        from snownlp import SnowNLP

        s = SnowNLP(content)
        sentences = s.sentences
        if not sentences:
            return content

        target_count = max(1, int(len(sentences) * target_ratio))
        summary = s.summary(target_count)
        if not summary:
            return content

        return "".join(summary)
    except Exception as e:
        logger.warning(f"[compress_text] SnowNLP failed: {e}, fallback to jieba\n")
        return _compress_text_jieba(content, target_ratio)


def _compress_text_jieba(content: str, target_ratio: float = 0.6) -> str:
    try:
        import jieba.analyse
    except ImportError:
        return content

    sentences = re.split(r"[。！？\n]", content)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return content

    keywords = set(jieba.analyse.extract_tags(content, topK=15))
    scored = []
    for s in sentences:
        score = sum(1 for w in keywords if w in s)
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)

    target_count = max(1, int(len(sentences) * target_ratio))
    kept = [s for _, s in scored[:target_count]]

    seen = set()
    ordered = []
    for s in sentences:
        if s in kept and s not in seen:
            ordered.append(s)
            seen.add(s)

    return "。".join(ordered) + "。" if ordered else content


def compress_notes_if_needed(notes: list[dict], target_ratio: float = 0.8, max_total_len: int = 5000) -> list[dict]:
    if not notes:
        return notes

    total_len = sum(len(n["content"]) for n in notes)
    if total_len <= max_total_len:
        return notes

    # Allocate the remaining budget fairly so every source is represented.
    # Extractive compression is attempted first, followed by a deterministic
    # hard clamp because model latency must not depend on summarizer quality.
    compressed_notes: list[dict] = []
    remaining = max(1, int(max_total_len))
    for index, note in enumerate(notes):
        remaining_notes = len(notes) - index
        budget = max(0, remaining // max(remaining_notes, 1))
        content = str(note.get("content") or "")
        if len(content) > budget:
            ratio = min(float(target_ratio), max(0.05, budget / max(len(content), 1)))
            content = _compress_text(content, ratio)
        content = _clamp_context(content, budget)
        compressed_notes.append(
            {
                "file_name": note.get("file_name", ""),
                "file_path": note.get("file_path", ""),
                "content": content,
            }
        )
        remaining -= len(content)
    return compressed_notes


def _clamp_context(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker = "\n\n[…内容已压缩…]\n\n"
    if max_chars <= len(marker) + 2:
        return text[:max_chars]
    available = max(1, max_chars - len(marker))
    head_len = max(1, int(available * 0.7))
    tail_len = max(0, available - head_len)
    return text[:head_len].rstrip() + marker + (text[-tail_len:].lstrip() if tail_len else "")


def _add_survey_frontmatter(topic: str, content: str) -> str:
    import yaml

    fm = {"topic": topic, "type": "survey", "tags": [topic]}
    fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{fm_str}\n---\n\n{content}"


def fix_existing_survey_topics() -> dict:
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    workspace_path = Path(workspace)
    fixed = 0
    skipped = 0

    for md_file in workspace_path.rglob("*.md"):
        if md_file.name.startswith("."):
            continue
        if not (md_file.name.endswith("_综述.md") or md_file.name.endswith("综述.md")):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(text)

            stem = md_file.stem
            topic_name = re.sub(r"[_\s]*综述$", "", stem).strip()
            if not topic_name:
                skipped += 1
                continue

            if fm and fm.get("topic") == topic_name:
                skipped += 1
                continue

            new_content = _add_survey_frontmatter(topic_name, body.strip())
            md_file.write_text(new_content, encoding="utf-8")
            fixed += 1
        except Exception:
            skipped += 1

    return {"success": True, "fixed": fixed, "skipped": skipped}


def generate_new_survey(topic: str, notes: list[dict], on_chunk=None) -> dict:
    from prompts import CASCADE_SURVEY_NEW_PROMPT
    from utils.llm_utils import APIConfigError, check_api_config

    try:
        is_valid, error_msg = check_api_config()
        if not is_valid:
            return {"success": False, "message": error_msg}
    except APIConfigError as e:
        return {"success": False, "message": str(e)}

    notes = compress_notes_if_needed(
        notes,
        target_ratio=0.8,
        max_total_len=_NEW_SURVEY_NOTES_MAX_CHARS,
    )

    notes_content = "\n\n---\n\n".join(f"### {n['file_name']}\n\n{n['content']}" for n in notes)

    prompt = CASCADE_SURVEY_NEW_PROMPT.format(topic_name=topic, notes_content=notes_content)

    try:
        from utils.llm_utils import call_llm_raw_stream

        full_text = call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=on_chunk)

        survey_path = get_survey_path(topic)
        if not survey_path:
            return {"success": False, "message": "主题名称非法"}

        survey_path.parent.mkdir(parents=True, exist_ok=True)
        survey_content = _add_survey_frontmatter(topic, full_text.strip())
        survey_path.write_text(survey_content, encoding="utf-8")

        append_changelog(f"生成综述: {config.ABSTRACT_FOLDER}/{_safe_topic_path(topic)}/{survey_path.name}")
        return {"success": True, "survey_path": str(survey_path)}
    except Exception as e:
        return {"success": False, "message": f"综述生成失败: {e}"}


def update_existing_survey(topic: str, new_notes: list[dict], on_chunk=None) -> dict:
    from prompts import CASCADE_SURVEY_UPDATE_PROMPT
    from utils.llm_utils import APIConfigError, check_api_config

    survey_path = get_survey_path(topic)
    if not survey_path or not survey_path.exists():
        return generate_new_survey(topic, new_notes, on_chunk)

    try:
        is_valid, error_msg = check_api_config()
        if not is_valid:
            return {"success": False, "message": error_msg}
    except APIConfigError as e:
        return {"success": False, "message": str(e)}

    existing_text = survey_path.read_text(encoding="utf-8")
    _fm, existing_body = parse_frontmatter(existing_text)

    new_notes = compress_notes_if_needed(
        new_notes,
        target_ratio=0.8,
        max_total_len=_UPDATE_SURVEY_NOTES_MAX_CHARS,
    )

    new_notes_content = "\n\n---\n\n".join(f"### {n['file_name']}\n\n{n['content']}" for n in new_notes)

    prompt = CASCADE_SURVEY_UPDATE_PROMPT.format(
        topic_name=topic,
        existing_survey=_clamp_context(existing_body, _EXISTING_SURVEY_MAX_CHARS),
        new_notes=new_notes_content,
    )

    try:
        from utils.llm_utils import call_llm_raw_stream

        full_text = call_llm_raw_stream(prompt, temperature=0.3, chunk_callback=on_chunk)

        survey_content = _add_survey_frontmatter(topic, full_text.strip())
        survey_path.write_text(survey_content, encoding="utf-8")

        append_changelog(f"更新综述: {config.ABSTRACT_FOLDER}/{_safe_topic_path(topic)}/{survey_path.name}")
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
    from utils.workspace_log import append_log

    with _changelog_lock:
        append_log("cascade", message)


def get_changelog(limit: int = 50) -> list[dict]:
    from utils.workspace_log import parse_log_entries

    rows = parse_log_entries(limit)
    return [
        {
            "timestamp": f"{row.get('date', '')} {row.get('time', '')}".strip(),
            "message": row.get("msg", ""),
        }
        for row in rows
    ]


def check_and_generate_surveys(on_progress=None) -> dict:
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    from utils.wiki_manager import parse_wiki_headings

    headings = parse_wiki_headings()
    if not headings:
        return {"success": True, "checked": 0, "generated": 0, "skipped": 0, "message": "没有找到任何主题"}

    survey_status = _read_survey_status_from_wiki()

    total = len(headings)
    generated = 0
    skipped = 0
    survey_skipped = 0
    errors = []

    for i, h in enumerate(headings):
        topic = h["name"]
        if on_progress:
            on_progress(i, total, f"检查主题「{topic}」...")

        if topic in ("AI 指南书",):
            skipped += 1
            continue

        is_on = survey_status.get(topic, True)
        if not is_on:
            survey_skipped += 1
            continue

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
            append_changelog(
                f"补生成综述: {config.ABSTRACT_FOLDER}/{_safe_topic_path(topic)}/{_safe_topic_segment(topic.rsplit(TOPIC_SEP, maxsplit=1)[-1])}_综述.md"
            )
        else:
            errors.append({"topic": topic, "error": result.get("message", "未知错误")})

    if on_progress:
        on_progress(
            total, total, f"完成：检查 {total} 个主题，生成 {generated} 篇综述，跳过 {survey_skipped} 篇（已关闭）"
        )

    return {
        "success": True,
        "checked": total,
        "generated": generated,
        "skipped": skipped,
        "survey_skipped": survey_skipped,
        "errors": errors,
    }


def _read_survey_status_from_wiki() -> dict:
    from sidecar.wiki_utils import get_survey_status

    return get_survey_status()
