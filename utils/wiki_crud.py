import re
import shutil
from datetime import datetime
from pathlib import Path

from config import config
from config.constants import TOPIC_SEP
from utils.logger import logger
from utils.topic_dedup import _deduplicate_files_in_wiki, _merge_duplicate_topics_in_wiki
from utils.wiki_manager import _get_wiki_path, _renumber_wiki_files, parse_wiki_headings, parse_wiki_structure


def add_file_to_wiki_topic(file_rel_path, topic, file_title=None):  # noqa: PLR0912, PLR0915
    wiki_path = _get_wiki_path()
    workspace = config.workspace_path
    if not wiki_path or not workspace:
        return False

    if "/" in topic and TOPIC_SEP not in topic:
        topic = topic.replace("/", TOPIC_SEP)

    display_title = file_title or Path(file_rel_path).stem

    try:
        if wiki_path.exists():
            content = wiki_path.read_text(encoding="utf-8")
        else:
            wiki_path.parent.mkdir(parents=True, exist_ok=True)
            content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"
    except Exception as e:
        logger.warning(f"[wiki] read failed: {e}")
        return False

    parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
    if not parts:
        return False
    topic_leaf = parts[-1]
    topic_depth = len(parts)
    heading_prefix = "#" * (topic_depth + 1)
    topic_heading = f"{heading_prefix} {topic_leaf}"

    lines = content.split("\n")
    file_item_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*$")

    insert_base = len(lines)
    for pi in range(len(parts) - 1):
        parent_label = parts[pi]
        parent_prefix = "#" * (pi + 2)
        parent_heading = f"{parent_prefix} {parent_label}"
        found = False
        for idx, line in enumerate(lines):
            if line.strip() == parent_heading:
                found = True
                insert_base = idx + 1
                break
        if not found:
            new_section = ["", parent_heading, ""]
            for j, sl in enumerate(new_section):
                lines.insert(insert_base + j, sl)
            insert_base += len(new_section)

    topic_start = None
    topic_end = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == topic_heading:
            topic_start = i
        elif topic_start is not None and re.match(r"^#{2,}\s+", stripped):
            h_level = len(re.match(r"^(#{2,})", stripped).group(1))
            if h_level <= topic_depth + 1:
                topic_end = i
                break

    if topic_start is None:
        new_section = ["", topic_heading, "", f"1. **{display_title}**"]
        for j, sl in enumerate(new_section):
            lines.insert(insert_base + j, sl)
    else:
        last_file_idx = topic_start
        for i in range(topic_start + 1, topic_end):
            if file_item_pattern.match(lines[i].strip()):
                last_file_idx = i

        for i in range(topic_start + 1, topic_end):
            fm = file_item_pattern.match(lines[i].strip())
            if fm and fm.group(2).strip() == display_title:
                return True

        lines.insert(last_file_idx + 1, f"0. **{display_title}**")

    _renumber_wiki_files(lines)

    try:
        new_content = "\n".join(lines)
        if not new_content.endswith("\n"):
            new_content += "\n"
        wiki_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"[wiki] write failed: {e}")
        return False


def rename_wiki_topic(old_topic, new_topic):  # noqa: PLR0912, PLR0915
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return False, []

    try:
        content = wiki_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"[rename_topic] read failed: {e}")
        return False, []

    lines = content.split("\n")
    file_item_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*$")
    new_lines = []
    in_target = False
    file_titles = []

    old_heading = f"## {old_topic}"
    new_heading = f"## {new_topic}"

    for line in lines:
        stripped = line.strip()
        if stripped == old_heading:
            in_target = True
            new_lines.append(new_heading)
            continue
        if in_target:
            if re.match(r"^#{2,}\s+", stripped):
                in_target = False
                new_lines.append(line)
                continue
            fm = file_item_pattern.match(stripped)
            if fm:
                file_titles.append(fm.group(2).strip())
            new_lines.append(line)
            continue
        new_lines.append(line)

    _renumber_wiki_files(new_lines)

    try:
        wiki_path.write_text("\n".join(new_lines), encoding="utf-8")

        workspace = config.workspace_path
        if workspace:
            old_dir = Path(workspace) / config.NOTES_FOLDER / old_topic
            new_dir = Path(workspace) / config.NOTES_FOLDER / new_topic
            if old_dir.exists() and old_dir.is_dir():
                if new_dir.exists():
                    for item in old_dir.iterdir():
                        dst = new_dir / item.name
                        if dst.exists():
                            if item.is_dir():
                                shutil.rmtree(str(dst))
                            else:
                                dst.unlink()
                        shutil.move(str(item), str(dst))
                    shutil.rmtree(str(old_dir))
                else:
                    old_dir.rename(new_dir)

        return True, file_titles
    except Exception as e:
        logger.warning(f"[rename_topic] write failed: {e}")
        return False, []


def _remove_topic_from_wiki(topic_name):
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return False, []

    try:
        content = wiki_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"[_remove_topic] read failed: {e}")
        return False, []

    lines = content.split("\n")
    file_item_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*$")
    new_lines = []
    in_target = False
    removed_titles = []
    target_heading = f"## {topic_name}"

    for line in lines:
        stripped = line.strip()
        if stripped == target_heading:
            in_target = True
            continue
        if in_target:
            if re.match(r"^#{2,}\s+", stripped):
                in_target = False
                new_lines.append(line)
                continue
            fm = file_item_pattern.match(stripped)
            if fm:
                removed_titles.append(fm.group(2).strip())
            continue
        new_lines.append(line)

    _renumber_wiki_files(new_lines)
    wiki_path.write_text("\n".join(new_lines), encoding="utf-8")
    return True, removed_titles


def remove_file_from_wiki_topic(file_rel_path):  # noqa: PLR0912
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return False, None

    try:
        content = wiki_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"[remove_file] read failed: {e}")
        return False, None

    target_title = Path(file_rel_path).stem
    lines = content.split("\n")
    file_item_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*$")
    old_topic = None
    current_topic = None
    new_lines = []

    for line in lines:
        stripped = line.strip()
        heading_match = re.match(r"^(#{2,})\s+(.+)$", stripped)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            if heading_text not in ("目录", "来源文件"):
                current_topic = heading_text
            new_lines.append(line)
            continue

        if current_topic:
            file_match = file_item_pattern.match(stripped)
            if file_match and file_match.group(2).strip() == target_title:
                old_topic = current_topic
                continue

        new_lines.append(line)

    if old_topic:
        _renumber_wiki_files(new_lines)

    try:
        new_content = "\n".join(new_lines)
        if not new_content.endswith("\n"):
            new_content += "\n"
        wiki_path.write_text(new_content, encoding="utf-8")
        return True, old_topic
    except Exception as e:
        logger.warning(f"[remove_file] write failed: {e}")
        return False, None


def create_topic(topic_name):  # noqa: PLR0912
    wiki_path = _get_wiki_path()
    workspace = config.workspace_path

    if not wiki_path or not workspace:
        return {"success": False, "message": "未设置工作区"}

    if not topic_name or not topic_name.strip():
        return {"success": False, "message": "主题名不能为空"}

    topic_name = topic_name.strip()
    if "/" in topic_name and TOPIC_SEP not in topic_name:
        topic_name = topic_name.replace("/", TOPIC_SEP)

    try:
        if wiki_path.exists():
            content = wiki_path.read_text(encoding="utf-8")
        else:
            wiki_path.parent.mkdir(parents=True, exist_ok=True)
            content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"

        for h in parse_wiki_headings():
            if h["name"].lower() == topic_name.lower():
                return {"success": False, "message": f"主题「{topic_name}」已存在"}

        parts = [p.strip() for p in topic_name.split(TOPIC_SEP) if p.strip()]
        if not parts:
            return {"success": False, "message": "主题名不能为空"}
        topic_leaf = parts[-1]
        heading_prefix = "#" * (len(parts) + 1)

        new_topic_lines = ["", f"{heading_prefix} {topic_leaf}", ""]
        lines = content.split("\n")

        insert_idx = len(lines)
        for pi in range(len(parts) - 1):
            parent_label = parts[pi]
            parent_prefix = "#" * (pi + 2)
            parent_heading = f"{parent_prefix} {parent_label}"
            found = False
            for i, line in enumerate(lines):
                if line.strip() == parent_heading:
                    found = True
                    insert_idx = i + 1
                    break
            if not found:
                for j, sl in enumerate(["", parent_heading, ""]):
                    lines.insert(insert_idx + j, sl)
                insert_idx += 3

        for j, sl in enumerate(new_topic_lines):
            lines.insert(insert_idx + j, sl)

        wiki_path.write_text("\n".join(lines), encoding="utf-8")

        notes_topic_dir = Path(workspace) / config.NOTES_FOLDER
        for part in parts:
            notes_topic_dir = notes_topic_dir / part
        notes_topic_dir.mkdir(parents=True, exist_ok=True)

        return {"success": True, "message": f"主题「{topic_name}」创建成功"}

    except Exception as e:
        logger.error(f"[create_topic] failed: {e}")
        return {"success": False, "message": f"创建失败: {e}"}


def delete_topic(topic_name):  # noqa: PLR0912, PLR0915
    from utils.topic_assigner import (  # noqa: PLC0415
        _clear_topic_in_file,
        _remove_empty_dir,
        auto_assign_topic_for_file,
    )

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    workspace_path = Path(workspace)
    notes_dir = workspace_path / config.NOTES_FOLDER
    parts = [p.strip() for p in topic_name.split(TOPIC_SEP) if p.strip()]
    notes_topic_dir = notes_dir
    for part in parts:
        notes_topic_dir = notes_topic_dir / part
    organized_topic_dir = workspace_path / config.ABSTRACT_FOLDER
    for part in parts:
        organized_topic_dir = organized_topic_dir / part

    actual_files = []
    if notes_topic_dir.exists() and notes_topic_dir.is_dir():
        for f in notes_topic_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() == ".md":
                actual_files.append(f)

    notes_root = notes_dir
    notes_root.mkdir(parents=True, exist_ok=True)
    moved_count = 0
    for src in actual_files:
        dst = notes_root / src.name
        if dst.exists():
            stem = src.stem
            suffix = src.suffix
            counter = 1
            while dst.exists():
                dst = notes_root / f"{stem}_{counter}{suffix}"
                counter += 1
        try:
            shutil.move(str(src), str(dst))
            moved_count += 1
        except Exception as e:
            logger.warning(f"[delete_topic] move file failed: {src} -> {dst}: {e}")

    if notes_topic_dir.exists():
        _remove_empty_dir(notes_topic_dir)
    if organized_topic_dir.exists():
        _remove_empty_dir(organized_topic_dir)

    wiki_ok, _ = _remove_topic_from_wiki(topic_name)
    if not wiki_ok:
        logger.warning(f"[delete_topic] WIKI.md removal failed for {topic_name}")

    notes_root_files = set()
    for src in actual_files:
        dst = notes_root / src.name
        stem = src.stem
        suffix = src.suffix
        candidate = notes_root / f"{stem}{suffix}"
        counter = 1
        while not candidate.exists():
            candidate = notes_root / f"{stem}_{counter}{suffix}"
            counter += 1
            max_conflict_attempts = 100
            if counter > max_conflict_attempts:
                candidate = None
                break
        if candidate and candidate.exists():
            notes_root_files.add(candidate)
        else:
            notes_root_files.add(notes_root / src.name)

    for fp in notes_root_files:
        if fp.exists():
            try:
                _clear_topic_in_file(str(fp))
            except Exception as e:
                logger.warning(f"[delete_topic] clear topic failed: {fp} - {e}")

    reassigned_count = 0
    pending_count = 0

    for fp in notes_root_files:
        if not fp.exists():
            continue
        try:
            result = auto_assign_topic_for_file(str(fp))
            if result and result.get("status") == "auto_assigned":
                reassigned_count += 1
            else:
                pending_count += 1
        except Exception as e:
            logger.warning(f"[delete_topic] reassign failed: {fp} - {e}")
            pending_count += 1

    return {
        "success": True,
        "message": f"已删除主题「{topic_name}」，{moved_count} 个文件移至 Notes 根目录，"
        f"重新分配 {reassigned_count} 个，{pending_count} 个待确认",
        "reassigned": reassigned_count,
        "pending": pending_count,
        "moved": moved_count,
    }


def rename_topic(old_topic, new_topic):  # noqa: PLR0911, PLR0912, PLR0915
    from utils.topic_assigner import write_topic_to_file  # noqa: PLC0415

    if not old_topic or not new_topic:
        return {"success": False, "message": "主题名不能为空"}

    if old_topic == new_topic:
        return {"success": True, "message": "主题名相同，无需修改", "updated": 0, "merged": False}

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    workspace_path = Path(workspace)

    headings = parse_wiki_headings()
    new_topic_exists = False
    for h in headings:
        if h["name"].lower() == new_topic.lower():
            new_topic_exists = True
            new_topic = h["name"]
            break

    if new_topic_exists:
        wiki_structure = parse_wiki_structure()
        old_topic_data = None
        for t in wiki_structure:
            if t["name"] == old_topic:
                old_topic_data = t
                break

        if not old_topic_data:
            return {"success": False, "message": f"主题「{old_topic}」不存在", "updated": 0, "merged": False}

        old_topic_parts = [p.strip() for p in old_topic.split(TOPIC_SEP) if p.strip()]
        old_topic_dir = workspace_path / config.NOTES_FOLDER
        for part in old_topic_parts:
            old_topic_dir = old_topic_dir / part

        old_file_titles = old_topic_data.get("files", [])
        for title in old_file_titles:
            fp = old_topic_dir / f"{title}.md"
            if fp.exists():
                write_topic_to_file(str(fp), new_topic)
                add_file_to_wiki_topic(str(fp), new_topic, title)

        _remove_topic_from_wiki(old_topic)
        _merge_duplicate_topics_in_wiki()
        _deduplicate_files_in_wiki()

        old_dir = workspace_path / config.NOTES_FOLDER / old_topic
        new_dir = workspace_path / config.NOTES_FOLDER / new_topic
        if old_dir.exists() and old_dir.is_dir():
            new_dir.mkdir(parents=True, exist_ok=True)
            for item in old_dir.iterdir():
                dst = new_dir / item.name
                if dst.exists():
                    if item.is_dir():
                        shutil.rmtree(str(dst))
                    else:
                        dst.unlink()
                shutil.move(str(item), str(dst))
            shutil.rmtree(str(old_dir))

        return {
            "success": True,
            "message": f"已合并到「{new_topic}」，移动 {len(old_file_titles)} 个文件",
            "updated": len(old_file_titles),
            "merged": True,
        }

    wiki_success, old_file_titles = rename_wiki_topic(old_topic, new_topic)

    old_topic_parts = [p.strip() for p in old_topic.split(TOPIC_SEP) if p.strip()]
    old_topic_dir = workspace_path / config.NOTES_FOLDER
    for part in old_topic_parts:
        old_topic_dir = old_topic_dir / part

    updated_count = 0
    for title in old_file_titles:
        full_path = old_topic_dir / f"{title}.md"
        if full_path.exists():
            try:
                write_topic_to_file(str(full_path), new_topic)
                updated_count += 1
            except Exception as e:
                logger.warning(f"[rename_topic] update YAML failed: {title} - {e}")

    if not wiki_success and updated_count == 0:
        return {"success": False, "message": "重命名失败", "merged": False}

    return {
        "success": True,
        "message": f"已重命名主题，更新 {updated_count} 个文件",
        "updated": updated_count,
        "merged": False,
    }
