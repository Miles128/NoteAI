import re

from utils.logger import logger
from utils.wiki_manager import _get_wiki_path, _renumber_wiki_files


def _remove_empty_topic_sections(topic_name_lower):
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return
    try:
        content = wiki_path.read_text(encoding="utf-8")
    except Exception:
        return
    lines = content.split("\n")
    result_lines = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            heading_name = stripped[3:].strip()
            if heading_name.lower() == topic_name_lower:
                section_lines = [lines[i]]
                has_files = False
                j = i + 1
                while j < len(lines):
                    s = lines[j].strip()
                    if s.startswith("## ") and not s.startswith("### "):
                        break
                    section_lines.append(lines[j])
                    if re.match(r"^\d+\.\s+\*\*", s):
                        has_files = True
                    j += 1
                if has_files:
                    result_lines.extend(section_lines)
                i = j
                continue
        result_lines.append(lines[i])
        i += 1
    try:
        new_content = "\n".join(result_lines)
        if not new_content.endswith("\n"):
            new_content += "\n"
        wiki_path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        logger.warning(f"[topic_assigner] 写入 WIKI.md 失败: {e}")


def _merge_duplicate_topics_in_wiki():  # noqa: PLR0912, PLR0915
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return 0

    try:
        content = wiki_path.read_text(encoding="utf-8")
    except Exception:
        return 0

    lines = content.split("\n")
    file_item_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*$")

    sections = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if re.match(r"^## (?!目录)", stripped):
            heading_name = stripped[3:].strip()
            section_lines = [lines[i]]
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if re.match(r"^## (?!目录)", s):
                    break
                section_lines.append(lines[j])
                j += 1
            sections.append({"name": heading_name, "start": i, "end": j, "lines": section_lines})
            i = j
        else:
            i += 1

    groups = {}
    for sec in sections:
        key = sec["name"].lower()
        groups.setdefault(key, []).append(sec)

    merged = 0
    for group in groups.values():
        if len(group) <= 1:
            continue
        keeper = group[0]
        seen_titles = set()
        for line in keeper["lines"]:
            fm = file_item_pattern.match(line.strip())
            if fm:
                seen_titles.add(fm.group(2).strip())

        for dup in group[1:]:
            for line in dup["lines"]:
                fm = file_item_pattern.match(line.strip())
                if fm and fm.group(2).strip() not in seen_titles:
                    seen_titles.add(fm.group(2).strip())
                    keeper["lines"].append(f"{len(seen_titles)}. **{fm.group(2)}**")
            merged += 1

    if merged == 0:
        return 0

    remove_ranges = set()
    keeper_starts = {}
    for group in groups.values():
        if len(group) > 1:
            keeper = group[0]
            keeper_starts[keeper["start"]] = keeper["lines"]
            for dup in group:
                for idx in range(dup["start"], dup["end"]):
                    remove_ranges.add(idx if dup is not keeper else -1)
            for idx in range(keeper["start"], keeper["end"]):
                remove_ranges.discard(idx)

    new_lines = []
    for i, line in enumerate(lines):
        if i in remove_ranges:
            continue
        if i in keeper_starts:
            for sl in keeper_starts[i]:
                new_lines.append(sl)
            continue
        new_lines.append(line)

    _renumber_wiki_files(new_lines)
    wiki_path.write_text("\n".join(new_lines), encoding="utf-8")
    return merged


def _deduplicate_files_in_wiki():
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return 0

    try:
        content = wiki_path.read_text(encoding="utf-8")
    except Exception:
        return 0

    lines = content.split("\n")
    file_item_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*$")
    new_lines = []
    i = 0
    removed = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        is_heading = bool(re.match(r"^#{2,}\s+", stripped)) and stripped[2:].strip() not in ("目录", "来源文件")

        if is_heading:
            new_lines.append(line)
            seen = set()
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if re.match(r"^#{2,}\s+", s):
                    break
                fm = file_item_pattern.match(s)
                if fm:
                    title = fm.group(2).strip()
                    if title not in seen:
                        seen.add(title)
                        new_lines.append(lines[j])
                    else:
                        removed += 1
                else:
                    new_lines.append(lines[j])
                j += 1
            i = j
        else:
            new_lines.append(line)
            i += 1

    if removed > 0:
        _renumber_wiki_files(new_lines)
        wiki_path.write_text("\n".join(new_lines), encoding="utf-8")
    return removed
