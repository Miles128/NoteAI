import re
import json
import sys
import threading
from pathlib import Path

from utils.activity_log import add_entry as _log
from config.settings import config
from utils.logger import logger

from utils.text_utils import tokenize as tokenize_text, _is_meaningful_tag, _normalize_for_match, _is_generic_word
# WIKI.md 操作从 utils.wiki_manager 导入
from utils.wiki_manager import (
    _get_wiki_path, parse_wiki_headings, parse_wiki_structure,
    add_file_to_wiki_topic, remove_file_from_wiki_topic,
    rename_wiki_topic, _remove_topic_from_wiki,
    _merge_duplicate_topics_in_wiki, _deduplicate_files_in_wiki,
    _remove_empty_topic_sections, create_topic, rename_topic,
    delete_topic, sync_wiki_with_files,
)

_pending_lock = threading.Lock()


def _get_pending_path():
    workspace = config.workspace_path
    if not workspace:
        return None
    return Path(workspace) / ".pending_topics.json"


def load_pending():
    with _pending_lock:
        path = _get_pending_path()
        if not path or not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError, ValueError) as e:
            sys.stderr.write(f"[topic_assigner] load_pending failed: {e}\n")
            sys.stderr.flush()
            return []


def save_pending(pending):
    with _pending_lock:
        path = _get_pending_path()
        if not path:
            return
        tmp_path = path.with_suffix('.tmp')
        tmp_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp_path.replace(path)


def cleanup_stale_pending():
    workspace = config.workspace_path
    if not workspace:
        return 0
    pending = load_pending()
    if not pending:
        return 0
    ws = Path(workspace)
    original_count = len(pending)
    valid = []
    seen = set()
    for p in pending:
        file_path = p.get("file", "")
        if not file_path:
            continue
        if file_path in seen:
            continue
        seen.add(file_path)
        full = ws / file_path if not Path(file_path).is_absolute() else Path(file_path)
        if not full.exists():
            logger.info(f"[topic_assigner] 清理无效待办: {file_path} 文件已不存在")
            continue
        try:
            text = full.read_text(encoding='utf-8')
            m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
            if m and not _check_topic_needs_processing(m.group(1)):
                logger.info(f"[topic_assigner] 清理已处理待办: {file_path} 已有主题")
                continue
        except Exception as e:
            sys.stderr.write(f"[cleanup_stale] read failed: {e}\n"); sys.stderr.flush()
        valid.append(p)
    removed = original_count - len(valid)
    if removed > 0:
        save_pending(valid)
    return removed


def _norm_topic(topic: str) -> str:
    """将传入的主题字符串规范化：移除旧式 / 分隔 → 统一用  >"""
    from config.constants import TOPIC_SEP
    clean = topic.strip()
    if '/' in clean and TOPIC_SEP not in clean:
        clean = clean.replace('/', TOPIC_SEP)
    return clean


def write_topic_to_file(file_path, topic):
    topic = _norm_topic(topic)
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        bom = '\ufeff' if text.startswith('\ufeff') else ''
        clean = text.lstrip('\ufeff')
        m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', clean)
        if not m:
            import yaml
            frontmatter = '---\ntopic: ' + yaml.dump(topic, allow_unicode=True, default_flow_style=True).strip() + '\n---\n'
            Path(file_path).write_text(bom + frontmatter + clean, encoding='utf-8')
            return {"success": True}
        yaml_text = m.group(2)
        lines = yaml_text.split('\n')
        found = False
        for i, line in enumerate(lines):
            idx = line.find(':')
            if idx < 0:
                continue
            key = line[:idx].strip()
            if key == 'topic':
                import yaml
                lines[i] = 'topic: ' + yaml.dump(topic, allow_unicode=True, default_flow_style=True).strip()
                found = True
                break
        if not found:
            lines.append(f'topic: {topic}')
        new_yaml = '\n'.join(lines)
        new_text = bom + m.group(1) + new_yaml + m.group(3) + clean[m.end():]
        Path(file_path).write_text(new_text, encoding='utf-8')
        return {"success": True}
    except Exception as e:
        sys.stderr.write(f"[write_topic] failed: {e}\n")
        sys.stderr.flush()
        return {"success": False, "message": str(e)}


def move_file_to_notes_topic_folder(file_path, topic):
    topic = _norm_topic(topic)
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    src = Path(file_path)
    if not src.exists():
        src = Path(workspace) / file_path
    if not src.exists():
        return {"success": False, "message": f"文件不存在: {file_path}"}

    import shutil
    from config.constants import TOPIC_SEP

    clean = topic.replace('..', '').strip()
    if not clean:
        return {"success": False, "message": "主题名称非法"}

    parts = [p.strip() for p in clean.split(TOPIC_SEP) if p.strip()]
    if not parts:
        return {"success": False, "message": "主题名称非法"}

    topic_dir = Path(workspace) / config.NOTES_FOLDER
    for part in parts:
        topic_dir = topic_dir / part
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
        return {"success": True, "message": f"已移动到 {new_rel}", "new_path": new_rel}
    except Exception as e:
        return {"success": False, "message": f"文件移动失败: {e}"}


def _check_topic_needs_processing(yaml_text: str) -> bool:
    """
    检查文件的 topic 状态是否需要处理
    返回 True 如果：
    - 没有 topic 标签
    - 或 topic 标签为空
    - 或 topic 标签不唯一（列表形式有多个值）
    """
    has_topic = False
    topic_value = None
    
    for line in yaml_text.split('\n'):
        idx = line.find(':')
        if idx < 0:
            continue
        key = line[:idx].strip()
        val = line[idx + 1:].strip()
        if key == 'topic':
            has_topic = True
            topic_value = val
            break
    
    if not has_topic:
        return True
    
    if not topic_value or topic_value.strip() == '':
        return True
    
    if topic_value.startswith('[') and topic_value.endswith(']'):
        items = [t.strip().strip("'\"") for t in topic_value[1:-1].split(',') if t.strip()]
        if len(items) > 1:
            return True
        if len(items) == 0:
            return True
    
    return False


def _find_best_topic_match(hint: str, headings: list) -> str:
    hint_norm = _normalize_for_match(hint)
    hint_tokens = tokenize_text(hint)

    for h in headings:
        if _normalize_for_match(h["name"]) == hint_norm:
            return h["name"]

    for h in headings:
        name_norm = _normalize_for_match(h["name"])
        if hint_norm in name_norm or name_norm in hint_norm:
            return h["name"]

    best_score = 0
    best_topic = None
    for h in headings:
        topic_tokens = tokenize_text(h["name"])
        score = 0
        for ht in hint_tokens:
            if _is_meaningful_tag(ht):
                for tt in topic_tokens:
                    if _normalize_for_match(ht) == _normalize_for_match(tt):
                        score += 2
        if _has_consecutive_two_words_match(topic_tokens, hint):
            score += 3
        if _has_consecutive_two_words_match(hint_tokens, h["name"]):
            score += 3
        if score > best_score:
            best_score = score
            best_topic = h["name"]

    if best_topic and best_score >= 2:
        return best_topic

    return None


def _has_consecutive_two_words_match(topic_tokens: list, filename: str) -> bool:
    """
    第一优先级匹配：主题分词后是否有连续的两个词在文件名中出现（忽略空格）
    例如：主题["机器", "学习", "基础"] → 检查"机器学习"、"学习基础"是否在文件名中
    """
    filename_norm = _normalize_for_match(filename)

    for i in range(len(topic_tokens) - 1):
        word1 = topic_tokens[i]
        word2 = topic_tokens[i + 1]
        combined = _normalize_for_match(word1 + word2)
        if combined in filename_norm:
            return True

    return False


def _has_meaningful_word_match(word: str, topic_name: str) -> bool:
    """
    检查单词是否足够有意义且在主题名中出现（忽略空格）
    """
    if not _is_meaningful_tag(word):
        return False

    return _normalize_for_match(word) in _normalize_for_match(topic_name)


def _needs_format_optimization(body):
    if not body or not body.strip():
        return False
    has_sub_heading = bool(re.search(r'^#{2,3}\s+\S', body, re.MULTILINE))
    if has_sub_heading:
        return False
    has_punctuation = bool(re.search(r'[，,。.！!？?；;：:、]', body))
    if has_punctuation:
        return False
    return True


def _optimize_file_format(full_path, text, m):
    from utils.helpers import smart_format_markdown

    body = text
    title = full_path.stem
    if m:
        body = text[m.end():]
        for line in m.group(1).split('\n'):
            idx = line.find(':')
            if idx < 0:
                continue
            key = line[:idx].strip()
            val = line[idx + 1:].strip()
            if key == 'title':
                title = val.strip().strip("'\"")
                break

    if not _needs_format_optimization(body):
        return False

    optimized_body = smart_format_markdown(body, title)
    if optimized_body == body:
        return False

    if m:
        import yaml as _yaml
        try:
            fm = _yaml.safe_load(m.group(1))
        except Exception:
            fm = None
        if fm and isinstance(fm, dict):
            fm_str = _yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
            new_content = '---\n' + fm_str + '\n---\n' + optimized_body
        else:
            new_content = optimized_body
    else:
        new_content = optimized_body

    try:
        full_path.write_text(new_content, encoding='utf-8')
        return True
    except (OSError, ValueError) as e:
        sys.stderr.write(f"[topic_assigner] _optimize_file_format write failed: {e}\n")
        sys.stderr.flush()
        return False


def _llm_suggest_topic(title, tags, content_preview, topic_names):
    if not config.api_key:
        return []
    if not topic_names:
        return []

    from utils.llm_utils import call_llm
    from prompts.topic_assignment import TOPIC_SUGGESTION_PROMPT

    tags_str = ", ".join(tags) if tags else "无"
    topic_list_str = "\n".join(f"- {t}" for t in topic_names)

    prompt = TOPIC_SUGGESTION_PROMPT.format(title=title, tags=tags_str)

    prompt += f"\n\n已有的主题分类列表（请优先从中选择）：\n{topic_list_str}"

    prompt += f"\n\n文章内容预览：\n{content_preview}"

    try:
        result = call_llm(prompt, temperature=0.3)
        suggested = []
        for line in result.strip().split('\n'):
            line = line.strip().lstrip('-•*0-9. ').strip()
            if not line:
                continue
            for tn in topic_names:
                if _normalize_for_match(line) == _normalize_for_match(tn):
                    suggested.append(tn)
                    break
            else:
                if line and len(line) <= 20:
                    suggested.append(line)
        return suggested[:4]
    except Exception as e:
        sys.stderr.write(f"[llm_suggest_topic] failed: {e}\n")
        sys.stderr.flush()
        return []


def _workspace_rel(path: Path, workspace: str) -> str:
    return str(path.relative_to(workspace)) if path.is_relative_to(workspace) else str(path)


def _extract_assignment_meta(full_path: Path, match) -> tuple[str, list[str], str]:
    yaml_text = match.group(1) if match else ''
    tags = []
    title = full_path.stem
    if not match:
        return title, tags, yaml_text

    for line in yaml_text.split('\n'):
        idx = line.find(':')
        if idx < 0:
            continue
        key = line[:idx].strip()
        val = line[idx + 1:].strip()
        if key == 'tags' and val.startswith('[') and val.endswith(']'):
            tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
        elif key == 'title':
            title = val.strip().strip("'\"")
    return title, tags, yaml_text


def _apply_auto_topic(full_path: Path, workspace: str, topic: str, title: str, source: str | None, format_optimized: bool):
    write_topic_to_file(str(full_path), topic)
    add_file_to_wiki_topic(_workspace_rel(full_path, workspace), topic, title)
    move_file_to_notes_topic_folder(str(full_path), topic)
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


def _collect_topic_candidates(headings, filename: str, tags: list[str]):
    high_priority_candidates = []
    low_priority_candidates = []
    normalized_filename = _normalize_for_match(filename)

    for heading in headings:
        h_name = heading["name"]
        topic_tokens = tokenize_text(h_name)
        if _has_consecutive_two_words_match(topic_tokens, filename):
            high_priority_candidates.append(heading)
            continue
        if any(_has_meaningful_word_match(tag, h_name) for tag in tags):
            if heading not in low_priority_candidates:
                low_priority_candidates.append(heading)
            continue
        for token in topic_tokens:
            if _is_meaningful_tag(token) and _normalize_for_match(token) in normalized_filename:
                if heading not in low_priority_candidates and heading not in high_priority_candidates:
                    low_priority_candidates.append(heading)
                break

    candidates = [h["name"] for h in high_priority_candidates]
    extra_candidates = [h["name"] for h in low_priority_candidates if h["name"] not in candidates]
    for raw in [*tags, *tokenize_text(filename)]:
        if _is_meaningful_tag(raw) and not _is_generic_word(raw) and raw not in candidates and raw not in extra_candidates:
            extra_candidates.append(raw)
    return high_priority_candidates, candidates, extra_candidates


def _match_llm_suggestions(llm_suggestions, headings):
    matched = []
    for suggestion in llm_suggestions:
        for heading in headings:
            if _normalize_for_match(suggestion) == _normalize_for_match(heading["name"]):
                matched.append(heading["name"])
                break
    return matched


def _load_assignment_text(full_path: Path):
    try:
        text = full_path.read_text(encoding='utf-8')
    except Exception:
        return None, None, "", [], ""
    match = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
    title, tags, yaml_text = _extract_assignment_meta(full_path, match)
    return text, match, title, tags, yaml_text


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
    text, match, title, tags, yaml_text = _load_assignment_text(full_path)
    if text is None:
        return None

    if match and not _check_topic_needs_processing(yaml_text):
        return None

    format_optimized = False

    survey_result = _try_assign_survey(full_path, workspace, title, format_optimized)
    if survey_result:
        return survey_result

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


def _remove_empty_dir(dir_path):
    """递归删除空目录"""
    import shutil
    dir_path = Path(dir_path)
    if not dir_path.exists():
        return
    try:
        shutil.rmtree(str(dir_path))
    except Exception as e:
        sys.stderr.write(f"[delete_topic] remove dir failed: {dir_path} - {e}\n")
        sys.stderr.flush()


def _clear_topic_in_file(file_path):
    """清除文件 YAML 中的 topic 字段"""
    text = Path(file_path).read_text(encoding='utf-8')
    bom = '\ufeff' if text.startswith('\ufeff') else ''
    clean = text.lstrip('\ufeff')
    m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', clean)
    if not m:
        return

    yaml_text = m.group(2)
    lines = yaml_text.split('\n')
    new_lines = []
    for line in lines:
        idx = line.find(':')
        if idx >= 0:
            key = line[:idx].strip()
            if key == 'topic':
                continue
        new_lines.append(line)

    new_yaml = '\n'.join(new_lines)
    new_content = bom + m.group(1) + new_yaml + m.group(3) + clean[m.end():]
    Path(file_path).write_text(new_content, encoding='utf-8')


def move_file_to_topic(file_rel_path, new_topic, file_title=None):
    new_topic = _norm_topic(new_topic)
    """
    移动文件到新主题：
    1. 从原主题的 WIKI.md 中移除文件记录
    2. 将文件添加到新主题的 WIKI.md
    3. 更新文件 YAML 的 topic 字段
    
    返回: {"success": bool, "message": str}
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    file_path = Path(workspace) / file_rel_path
    if not file_path.exists():
        return {"success": False, "message": f"文件不存在: {file_rel_path}"}

    if file_title is None:
        try:
            text = file_path.read_text(encoding='utf-8')
            m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
            if m:
                yaml_text = m.group(1)
                for line in yaml_text.split('\n'):
                    idx = line.find(':')
                    if idx >= 0:
                        key = line[:idx].strip()
                        if key == 'title':
                            file_title = line[idx + 1:].strip().strip("'\"")
                            break
            if file_title is None:
                file_title = file_path.stem
        except Exception:
            file_title = file_path.stem

    remove_success, old_topic = remove_file_from_wiki_topic(file_rel_path)

    add_success = add_file_to_wiki_topic(file_rel_path, new_topic, file_title)

    write_topic_to_file(str(file_path), new_topic)

    move_file_to_notes_topic_folder(str(file_path), new_topic)

    if add_success:
        if old_topic:
            return {"success": True, "message": f"已从「{old_topic}」移动到「{new_topic}」"}
        else:
            return {"success": True, "message": f"已添加到「{new_topic}」"}
    else:
        return {"success": False, "message": "移动失败"}


def _read_topic_from_file(file_path):
    """
    从文件的 YAML frontmatter 中读取 topic 字段
    返回: topic 字符串（如果没有则返回 None）
    """
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', text.lstrip('\ufeff'))
        if not m:
            return None
        yaml_text = m.group(2)
        for line in yaml_text.split('\n'):
            idx = line.find(':')
            if idx < 0:
                continue
            key = line[:idx].strip()
            val = line[idx + 1:].strip()
            if key == 'topic':
                if val and val.strip():
                    return _norm_topic(val.strip())
                return None
        return None
    except Exception as e:
        sys.stderr.write(f"[_read_topic] failed: {e}\n")
        sys.stderr.flush()
        return None


def _read_title_from_file(file_path):
    """
    从文件的 YAML frontmatter 中读取 title 字段
    返回: title 字符串（如果没有则返回文件名）
    """
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', text.lstrip('\ufeff'))
        if m:
            yaml_text = m.group(2)
            for line in yaml_text.split('\n'):
                idx = line.find(':')
                if idx < 0:
                    continue
                key = line[:idx].strip()
                val = line[idx + 1:].strip()
                if key == 'title':
                    if val and val.strip():
                        return val.strip().strip("'\"")
        return Path(file_path).stem
    except Exception:
        return Path(file_path).stem

