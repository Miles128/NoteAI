import re
from pathlib import Path

from utils.activity_log import add_entry as _log
from config.constants import TOPIC_SEP
from config.settings import ABSTRACT_FOLDER, NOTES_FOLDER, config
from utils.logger import logger

from utils.text_utils import tokenize as tokenize_text, _is_meaningful_tag, _normalize_for_match, _is_generic_word, parse_frontmatter
from utils.wiki_manager import (
    _get_wiki_path, parse_wiki_headings, parse_wiki_structure,
    add_file_to_wiki_topic, remove_file_from_wiki_topic,
    rename_wiki_topic, _remove_topic_from_wiki,
    _merge_duplicate_topics_in_wiki, _deduplicate_files_in_wiki,
    _remove_empty_topic_sections, create_topic, rename_topic,
    delete_topic, sync_wiki_with_files,
)
from utils.wiki_sync import topic_from_notes_path, _write_file_topic_from_folder

from utils.topic_classifier import (
    _norm_topic,
    _find_best_topic_match,
    _llm_suggest_topic,
    _collect_topic_candidates,
    _match_llm_suggestions,
)
from utils.topic_file_ops import (
    write_topic_to_file,
    _clear_topic_in_file,
    _read_topic_from_file,
    _read_title_from_file,
    move_file_to_notes_topic_folder,
    move_file_to_topic,
    _remove_empty_dir,
    _optimize_file_format,
    _needs_format_optimization,
    _check_topic_needs_processing,
)
from utils.topic_pending import (
    _get_pending_path,
    load_pending,
    save_pending,
    _drop_pending_for_rel,
    cleanup_stale_pending,
)


def _infer_topic_from_notes_folder(full_path: Path, workspace: str) -> str | None:
    ws = Path(workspace).resolve()
    try:
        rel = full_path.resolve().relative_to(ws)
    except ValueError:
        try:
            rel = full_path.relative_to(Path(workspace))
        except ValueError:
            return None

    parts = rel.parts
    if len(parts) < 3:
        return None
    if parts[0] != config.NOTES_FOLDER:
        return None

    dir_parts = parts[1:-1]
    if not dir_parts:
        return None
    if any(seg.startswith(".") for seg in dir_parts):
        return None

    trimmed = dir_parts[:3]
    return TOPIC_SEP.join(trimmed)


def _workspace_rel(path: Path, workspace: str) -> str:
    return str(path.relative_to(workspace)) if path.is_relative_to(workspace) else str(path)


def _extract_assignment_meta(full_path: Path, meta) -> tuple[str, list[str]]:
    tags = []
    title = full_path.stem
    if not meta:
        return title, tags

    t = meta.get('title')
    if t and isinstance(t, str):
        title = t
    raw_tags = meta.get('tags', [])
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if t]
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags = [raw_tags.strip()]
    return title, tags


def _apply_auto_topic(full_path: Path, workspace: str, topic: str, title: str, source: str | None, format_optimized: bool):
    write_topic_to_file(str(full_path), topic)
    add_file_to_wiki_topic(_workspace_rel(full_path, workspace), topic, title)
    move_file_to_notes_topic_folder(str(full_path), topic)
    _drop_pending_for_rel(_workspace_rel(full_path, workspace))
    prefix = "AI 分配" if source == "llm" else "自动分配"
    _log("topic_auto", f"{prefix}主题「{topic}」→ {full_path.name}", full_path.name)
    result = {"status": "auto_assigned", "topic": topic, "format_optimized": format_optimized}
    if source:
        result["source"] = source
    return result


def _save_pending_assignment(full_path: Path, workspace: str, title: str, tags: list[str], candidates: list[str], source: str, format_optimized: bool):
    pending = load_pending()
    rel = _workspace_rel(full_path, workspace)
    existing = next((p for p in pending if p.get("file") == rel), None)
    payload = {"file": rel, "title": title, "tags": tags, "candidates": candidates, "source": source}
    if existing:
        existing.update(payload)
    else:
        pending.append(payload)
    save_pending(pending)
    return {"status": "pending", "source": source, "format_optimized": format_optimized}


def _load_assignment_text(full_path: Path):
    try:
        text = full_path.read_text(encoding='utf-8')
    except Exception:
        return None, None, "", []
    meta, body = parse_frontmatter(text)
    title, tags = _extract_assignment_meta(full_path, meta)
    return text, meta, title, tags


def _try_assign_survey(full_path: Path, workspace: str, title: str, format_optimized: bool):
    filename = full_path.stem
    if not (filename.endswith('综述') or filename.endswith('_综述')):
        return None
    survey_hint = re.sub(r'[_\s]*综述$', '', filename).strip()
    if not survey_hint:
        return None
    best_match = _find_best_topic_match(survey_hint, parse_wiki_headings())
    if not best_match:
        return None
    return _apply_auto_topic(full_path, workspace, best_match, title, "survey", format_optimized)


def _try_assign_single_candidate(
    full_path: Path,
    workspace: str,
    title: str,
    candidates: list[str],
    high_priority_candidates: list,
    format_optimized: bool,
):
    if high_priority_candidates and len(candidates) == 1:
        return _apply_auto_topic(full_path, workspace, candidates[0], title, None, format_optimized)
    return None


def _try_assign_with_llm(
    full_path: Path,
    workspace: str,
    text: str,
    match,
    title: str,
    tags: list[str],
    headings,
    format_optimized: bool,
):
    body = text[match.end():] if match else text
    content_preview = body[:1500].strip()
    topic_names = [h["name"] for h in headings]
    llm_suggestions = _llm_suggest_topic(title, tags, content_preview, topic_names)
    if not llm_suggestions:
        return None, []
    matched = _match_llm_suggestions(llm_suggestions, headings)
    if len(matched) == 1:
        return _apply_auto_topic(full_path, workspace, matched[0], title, "llm", format_optimized), matched
    return None, [*matched, *llm_suggestions]


def _auto_assign_existing_file(full_path: Path, workspace: str, use_llm=True):  # noqa: PLR0911
    text, meta, title, tags = _load_assignment_text(full_path)
    if text is None:
        return None

    if meta is not None and not _check_topic_needs_processing(meta):
        return None

    format_optimized = False

    survey_result = _try_assign_survey(full_path, workspace, title, format_optimized)
    if survey_result:
        return survey_result

    folder_topic = _infer_topic_from_notes_folder(full_path, workspace)
    if folder_topic:
        return _apply_auto_topic(full_path, workspace, folder_topic, title, "folder_path", format_optimized)

    headings = parse_wiki_headings()
    if not headings:
        return _save_pending_assignment(full_path, workspace, title, tags, [], "none", format_optimized)

    high_priority_candidates, candidates, extra_candidates = _collect_topic_candidates(headings, full_path.stem, tags)
    single_candidate_result = _try_assign_single_candidate(
        full_path, workspace, title, candidates, high_priority_candidates, format_optimized
    )
    if single_candidate_result:
        return single_candidate_result

    all_candidates = candidates + extra_candidates
    need_llm = use_llm and config.api_key and (not high_priority_candidates or len(all_candidates) > 1)

    if need_llm:
        llm_result, llm_candidates = _try_assign_with_llm(
            full_path, workspace, text, match, title, tags, headings, format_optimized
        )
        if llm_result:
            return llm_result
        for candidate in llm_candidates:
            if candidate not in all_candidates:
                all_candidates.append(candidate)

    source = "llm" if need_llm else ("wiki" if high_priority_candidates else "low_priority")
    return _save_pending_assignment(full_path, workspace, title, tags, all_candidates, source, format_optimized)


def auto_assign_topic_for_file(file_path, use_llm=True):
    workspace = config.workspace_path
    if not workspace:
        return None

    full_path = Path(file_path)
    if not full_path.exists():
        return None

    return _auto_assign_existing_file(full_path, workspace, use_llm)


def auto_process_md_file(file_path, send_event=None, mark_wiki_sync=None):  # noqa: PLR0912
    """自动处理新建/移动的 Markdown 文件：对齐主题、自动分配、移动到正确目录。

    Args:
        file_path: Markdown 文件路径
        send_event: 可选回调，用于向前端发送事件，签名为 send_event(event_dict)
        mark_wiki_sync: 可选回调，用于标记需要 wiki 同步，签名为 mark_wiki_sync()
    """
    path = Path(file_path)
    try:
        text = path.read_text(encoding='utf-8')
    except Exception as e:
        logger.warning(f"[watcher] failed to read {file_path}: {e}\n")
        return

    meta, body = parse_frontmatter(text)

    folder_topic = topic_from_notes_path(path)
    if folder_topic:
        file_topic = meta.get("topic") if meta else None
        if isinstance(file_topic, list):
            file_topic = file_topic[0] if len(file_topic) == 1 else None
        if isinstance(file_topic, str):
            file_topic = file_topic.strip() or None
        if meta is None or _check_topic_needs_processing(meta) or file_topic != folder_topic:
            try:
                if _write_file_topic_from_folder(path, folder_topic):
                    if mark_wiki_sync:
                        mark_wiki_sync()
            except Exception as e:
                logger.warning(f"[watcher] align topic from folder failed for {file_path}: {e}\n")
        return

    if meta is None or _check_topic_needs_processing(meta):
        try:
            result = auto_assign_topic_for_file(file_path)
            if result and result.get("status") == "auto_assigned" and result.get("topic"):
                sync_wiki_with_files()
                if send_event:
                    send_event({
                        "type": "auto_topic_assigned",
                        "file": file_path,
                        "topic": result["topic"],
                    })
        except Exception as e:
            logger.warning(f"[watcher] auto_assign_topic_for_file failed for {file_path}: {e}\n")
        return

    file_topic = meta.get('topic') if meta else None
    if isinstance(file_topic, list):
        file_topic = file_topic[0] if len(file_topic) == 1 else None

    if not file_topic:
        return

    workspace = config.workspace_path
    filename = Path(file_path).stem

    is_survey = filename.endswith('综述') or filename.endswith('_综述')
    if is_survey:
        expected_dir = Path(workspace) / ABSTRACT_FOLDER / file_topic
    else:
        expected_dir = Path(workspace) / NOTES_FOLDER / file_topic

    try:
        in_correct_folder = Path(file_path).is_relative_to(expected_dir)
    except AttributeError:
        in_correct_folder = str(Path(file_path)).startswith(str(expected_dir))

    if not in_correct_folder and not is_survey:
        move_result = move_file_to_notes_topic_folder(file_path, file_topic)
        if move_result.get("success"):
            new_path = move_result.get("new_path", "")
            sync_wiki_with_files()
            if send_event:
                send_event({
                    "type": "auto_file_moved",
                    "file": file_path,
                    "topic": file_topic,
                    "new_path": new_path,
                })
