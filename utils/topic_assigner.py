import re
import json
import sys
from pathlib import Path
from config.settings import config


def _get_pending_path():
    workspace = config.workspace_path
    if not workspace:
        return None
    return Path(workspace) / ".pending_topics.json"


def _get_wiki_path():
    workspace = config.workspace_path
    if not workspace:
        return None
    return Path(workspace) / "WIKI.md"


def load_pending():
    path = _get_pending_path()
    if not path or not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return []


def save_pending(pending):
    path = _get_pending_path()
    if not path:
        return
    path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding='utf-8')


def parse_wiki_headings():
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = Path(workspace) / "WIKI.md"
    if not wiki_path.exists():
        return []
    try:
        text = wiki_path.read_text(encoding='utf-8')
    except Exception:
        return []
    headings = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('## ') and not stripped.startswith('### '):
            headings.append({"level": 2, "name": stripped[3:].strip()})
        elif stripped.startswith('### '):
            headings.append({"level": 3, "name": stripped[4:].strip()})
    return headings


def parse_wiki_structure():
    """
    解析 WIKI.md 的主题结构，返回主题列表及其文件
    
    返回格式:
    [
        {
            "name": "主题名",
            "files": [
                {"title": "文件标题", "path": "相对路径"},
                ...
            ]
        },
        ...
    ]
    """
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = Path(workspace) / "WIKI.md"
    if not wiki_path.exists():
        return []
    try:
        text = wiki_path.read_text(encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"[parse_wiki] read failed: {e}\n")
        sys.stderr.flush()
        return []

    topics = []
    lines = text.split('\n')

    current_topic = None
    in_source_files = False
    current_file = None

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*(.+?)\s*$')

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('## ') and not stripped.startswith('### '):
            if current_topic:
                if current_file:
                    if current_file.get('path'):
                        current_topic['files'].append(current_file)
                    current_file = None
                if current_topic['files']:
                    topics.append(current_topic)
                current_topic = None
                in_source_files = False

            topic_name = stripped[3:].strip()
            if topic_name and topic_name != '目录':
                current_topic = {"name": topic_name, "files": []}
                in_source_files = False
                current_file = None
            continue

        if stripped.startswith('### ') and current_topic:
            if stripped[4:].strip() == '来源文件':
                in_source_files = True
                if current_file:
                    if current_file.get('path'):
                        current_topic['files'].append(current_file)
                    current_file = None
            else:
                in_source_files = False
                if current_file:
                    if current_file.get('path'):
                        current_topic['files'].append(current_file)
                    current_file = None
            continue

        if in_source_files and current_topic:
            file_match = file_item_pattern.match(stripped)
            if file_match:
                if current_file:
                    if current_file.get('path'):
                        current_topic['files'].append(current_file)
                file_title = file_match.group(2).strip()
                current_file = {"title": file_title, "path": ""}
                continue

            if current_file:
                path_match = source_path_pattern.match(stripped)
                if path_match:
                    current_file['path'] = path_match.group(1).strip()

    if current_topic:
        if current_file:
            if current_file.get('path'):
                current_topic['files'].append(current_file)
        if current_topic['files']:
            topics.append(current_topic)

    return topics


def write_topic_to_file(file_path, topic):
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', text.lstrip('\ufeff'))
        if not m:
            return
        yaml_text = m.group(2)
        lines = yaml_text.split('\n')
        found = False
        for i, line in enumerate(lines):
            idx = line.find(':')
            if idx < 0:
                continue
            key = line[:idx].strip()
            if key == 'topic':
                lines[i] = f'topic: {topic}'
                found = True
                break
        if not found:
            lines.append(f'topic: {topic}')
        new_yaml = '\n'.join(lines)
        prefix = '\ufeff' if text.startswith('\ufeff') else ''
        new_text = prefix + m.group(1) + new_yaml + m.group(3) + text.lstrip('\ufeff')[m.end():]
        Path(file_path).write_text(new_text, encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"[write_topic] failed: {e}\n")
        sys.stderr.flush()


def add_file_to_wiki_topic(file_rel_path, topic, file_title=None):
    """
    向 WIKI.md 添加文件到指定主题下
    
    格式:
    ## 主题名
    
    ### 来源文件
    
    1. **文件标题**
       - 文件名：xxx.md
       - 原始路径：Notes/xxx.md
    
    2. **文件标题2**
       - 文件名：xxx2.md
       - 原始路径：Notes/xxx2.md
    """
    wiki_path = _get_wiki_path()
    workspace = config.workspace_path
    if not wiki_path or not workspace:
        return False

    display_title = file_title or Path(file_rel_path).stem
    file_name = Path(file_rel_path).name

    try:
        if wiki_path.exists():
            content = wiki_path.read_text(encoding='utf-8')
        else:
            from datetime import datetime
            content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"
    except Exception as e:
        sys.stderr.write(f"[wiki] read failed: {e}\n")
        sys.stderr.flush()
        return False

    lines = content.split('\n')
    topic_heading = f'## {topic}'

    topic_start_idx = None
    source_files_idx = None
    topic_end_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == topic_heading:
            topic_start_idx = i
            source_files_idx = None
        elif topic_start_idx is not None and stripped == '### 来源文件':
            source_files_idx = i
        elif topic_start_idx is not None and stripped.startswith('## ') and not stripped.startswith('### '):
            topic_end_idx = i
            break

    if topic_end_idx is None and topic_start_idx is not None:
        topic_end_idx = len(lines)

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*(.+?)\s*$')

    if topic_start_idx is not None and source_files_idx is not None:
        max_index = 0
        for i in range(source_files_idx + 1, topic_end_idx):
            stripped = lines[i].strip()
            file_match = file_item_pattern.match(stripped)
            if file_match:
                idx = int(file_match.group(1))
                if idx > max_index:
                    max_index = idx
            path_match = source_path_pattern.match(stripped)
            if path_match and path_match.group(1).strip() == file_rel_path:
                return True

        next_index = max_index + 1

        insert_idx = topic_end_idx
        for i in range(source_files_idx + 1, topic_end_idx):
            stripped = lines[i].strip()
            file_match = file_item_pattern.match(stripped)
            if file_match:
                for j in range(i + 1, topic_end_idx):
                    next_stripped = lines[j].strip()
                    next_file_match = file_item_pattern.match(next_stripped)
                    if next_file_match:
                        insert_idx = j
                        break
                    if next_stripped.startswith('## '):
                        insert_idx = j
                        break
                if insert_idx == topic_end_idx:
                    insert_idx = topic_end_idx
                break

        new_lines = [
            f"{next_index}. **{display_title}**",
            f"   - 文件名：{file_name}",
            f"   - 原始路径：{file_rel_path}"
        ]

        for i, line in enumerate(new_lines):
            lines.insert(insert_idx + i, line)

    else:
        new_lines = [
            '',
            f'## {topic}',
            '',
            '### 来源文件',
            '',
            f"1. **{display_title}**",
            f"   - 文件名：{file_name}",
            f"   - 原始路径：{file_rel_path}"
        ]
        lines.extend(new_lines)

    try:
        new_content = '\n'.join(lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        wiki_path.write_text(new_content, encoding='utf-8')
        return True
    except Exception as e:
        sys.stderr.write(f"[wiki] write failed: {e}\n")
        sys.stderr.flush()
        return False


def auto_assign_topic_for_file(file_path):
    workspace = config.workspace_path
    if not workspace:
        return

    full_path = Path(file_path)
    if not full_path.exists():
        return

    try:
        text = full_path.read_text(encoding='utf-8')
    except Exception:
        return

    m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
    if not m:
        return

    yaml_text = m.group(1)
    tags = []
    title = full_path.stem

    for line in yaml_text.split('\n'):
        idx = line.find(':')
        if idx < 0:
            continue
        key = line[:idx].strip()
        val = line[idx + 1:].strip()
        if key == 'topic':
            return
        if key == 'tags' and val.startswith('[') and val.endswith(']'):
            tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
        elif key == 'title':
            title = val.strip().strip("'\"")

    headings = parse_wiki_headings()
    matched = []

    for h in headings:
        h_name = h["name"]
        tag_match = False
        for tag in tags:
            if tag.lower() in h_name.lower() or h_name.lower() in tag.lower():
                tag_match = True
                break
        if tag_match:
            matched.append(h)
            continue
        for i in range(len(h_name) - 2):
            if h_name[i:i + 3] in title:
                matched.append(h)
                break

    if len(matched) == 1:
        write_topic_to_file(str(full_path), matched[0]["name"])
        return

    if len(matched) >= 2:
        candidates = [h["name"] for h in matched]
    elif config.api_key:
        try:
            from utils.helpers import call_llm
            from prompts import TOPIC_SUGGESTION_PROMPT
            tags_str = ', '.join(tags) if tags else '无'
            result = call_llm(TOPIC_SUGGESTION_PROMPT, temperature=0.3, title=title, tags=tags_str)
            candidates = [c.strip() for c in result.strip().split('\n') if c.strip()][:4]
        except Exception:
            return
    else:
        return

    if not candidates:
        return

    pending = load_pending()
    rel = str(full_path.relative_to(workspace)) if full_path.is_relative_to(workspace) else str(full_path)
    pending.append({
        "file": rel,
        "title": title,
        "tags": tags,
        "candidates": candidates,
        "source": "wiki" if matched else "llm"
    })
    save_pending(pending)


def rename_wiki_topic(old_topic, new_topic):
    """
    重命名 WIKI.md 中的主题（包括标题和目录）
    
    返回: (success, updated_file_paths)
    - updated_file_paths: 该主题下所有文件的相对路径列表（用于后续更新 YAML）
    """
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return False, []

    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"[rename_topic] read failed: {e}\n")
        sys.stderr.flush()
        return False, []

    lines = content.split('\n')
    new_lines = []
    in_target_topic = False
    target_ended = False
    file_paths = []

    old_heading = f'## {old_topic}'
    new_heading = f'## {new_topic}'

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*(.+?)\s*$')

    current_file_has_path = False

    for line in lines:
        stripped = line.strip()

        if stripped == old_heading:
            in_target_topic = True
            target_ended = False
            new_lines.append(new_heading)
            continue

        if in_target_topic and not target_ended:
            if stripped.startswith('## ') and not stripped.startswith('### '):
                target_ended = True
                new_lines.append(line)
                continue

            file_match = file_item_pattern.match(stripped)
            if file_match:
                current_file_has_path = False

            path_match = source_path_pattern.match(stripped)
            if path_match:
                file_paths.append(path_match.group(1).strip())
                current_file_has_path = True

        new_lines.append(line)

    toc_line = None
    toc_start_idx = -1
    toc_end_idx = -1

    for i, line in enumerate(new_lines):
        stripped = line.strip()
        if stripped == '## 目录':
            toc_start_idx = i
            toc_end_idx = len(new_lines)
            for j in range(i + 1, len(new_lines)):
                if new_lines[j].strip().startswith('## ') and not new_lines[j].strip().startswith('### '):
                    toc_end_idx = j
                    break
            break

    if toc_start_idx >= 0:
        for i in range(toc_start_idx, toc_end_idx):
            stripped = new_lines[i].strip()
            if stripped.startswith('- [') and f'](#' in stripped:
                if f'](#{old_topic}' in stripped:
                    link_name = stripped[3:stripped.find(']')]
                    if link_name == old_topic:
                        new_lines[i] = f'- [{new_topic}](#{new_topic})'
                    break

    try:
        new_content = '\n'.join(new_lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        wiki_path.write_text(new_content, encoding='utf-8')
        return True, file_paths
    except Exception as e:
        sys.stderr.write(f"[rename_topic] write failed: {e}\n")
        sys.stderr.flush()
        return False, []


def rename_topic(old_topic, new_topic):
    """
    重命名主题：
    1. 重命名 WIKI.md 中的主题标题和目录链接
    2. 更新该主题下所有文件的 YAML topic 字段
    
    返回: {"success": bool, "message": str, "updated": int}
    """
    if not old_topic or not new_topic:
        return {"success": False, "message": "主题名不能为空"}

    if old_topic == new_topic:
        return {"success": True, "message": "主题名相同，无需修改", "updated": 0}

    wiki_success, file_paths = rename_wiki_topic(old_topic, new_topic)

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    workspace_path = Path(workspace)

    updated_count = 0
    for rel_path in file_paths:
        full_path = workspace_path / rel_path
        if full_path.exists():
            try:
                write_topic_to_file(str(full_path), new_topic)
                updated_count += 1
            except Exception as e:
                sys.stderr.write(f"[rename_topic] update YAML failed: {rel_path} - {e}\n")
                sys.stderr.flush()

    if not wiki_success and updated_count == 0:
        return {"success": False, "message": "重命名失败"}

    return {
        "success": True,
        "message": f"已重命名主题，更新 {updated_count} 个文件",
        "updated": updated_count
    }


def remove_file_from_wiki_topic(file_rel_path):
    """
    从 WIKI.md 中移除指定文件的记录（保留序号连续性）
    
    返回: (success, old_topic_name)
    - old_topic_name: 文件原来所在的主题名（如果找到）
    """
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return False, None

    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"[remove_file] read failed: {e}\n")
        sys.stderr.flush()
        return False, None

    lines = content.split('\n')
    new_lines = []

    current_topic = None
    in_source_files = False
    current_file_index = None
    current_file_contains_target = False
    file_item_buffer = []
    skip_count = 0
    old_topic = None

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*(.+?)\s*$')

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('## ') and not stripped.startswith('### '):
            if file_item_buffer:
                for buf_line in file_item_buffer:
                    new_lines.append(buf_line)
                file_item_buffer = []

            current_topic = stripped[3:].strip()
            in_source_files = False
            current_file_index = None
            current_file_contains_target = False
            skip_count = 0
            new_lines.append(line)
            continue

        if stripped == '### 来源文件':
            if file_item_buffer:
                for buf_line in file_item_buffer:
                    new_lines.append(buf_line)
                file_item_buffer = []

            in_source_files = True
            current_file_index = None
            current_file_contains_target = False
            skip_count = 0
            new_lines.append(line)
            continue

        if in_source_files and current_topic:
            file_match = file_item_pattern.match(stripped)
            if file_match:
                if file_item_buffer:
                    if current_file_contains_target:
                        old_topic = current_topic
                        skip_count += 1
                    else:
                        for buf_line in file_item_buffer:
                            new_lines.append(buf_line)
                    file_item_buffer = []

                current_file_index = int(file_match.group(1))
                current_file_contains_target = False
                file_item_buffer.append(line)
                continue

            path_match = source_path_pattern.match(stripped)
            if path_match and path_match.group(1).strip() == file_rel_path:
                current_file_contains_target = True
                if file_item_buffer:
                    file_item_buffer.append(line)
                continue

            if file_item_buffer:
                file_item_buffer.append(line)
                continue

        new_lines.append(line)

    if file_item_buffer:
        if current_file_contains_target:
            old_topic = current_topic
            skip_count += 1
        else:
            for buf_line in file_item_buffer:
                new_lines.append(buf_line)

    if skip_count > 0:
        def _renumber_lines(lines_list):
            result = []
            file_item_pattern_inner = re.compile(r'^(\s*)(\d+)\.\s+\*\*(.+?)\*\*\s*$')

            current_number = 0
            buffer = []
            in_section = False

            for line in lines_list:
                stripped = line.strip()
                if stripped == '### 来源文件':
                    in_section = True
                    current_number = 0
                    result.append(line)
                    continue

                if in_section:
                    if stripped.startswith('## ') and not stripped.startswith('### '):
                        in_section = False
                        if buffer:
                            for buf_line in buffer:
                                result.append(buf_line)
                            buffer = []
                        result.append(line)
                        continue

                    file_match_inner = file_item_pattern_inner.match(line)
                    if file_match_inner:
                        if buffer:
                            for buf_line in buffer:
                                result.append(buf_line)
                            buffer = []

                        current_number += 1
                        indent = file_match_inner.group(1)
                        title = file_match_inner.group(3)
                        new_line = f"{indent}{current_number}. **{title}**"
                        buffer.append(new_line)
                        continue

                    if buffer:
                        buffer.append(line)
                        continue

                result.append(line)

            if buffer:
                for buf_line in buffer:
                    result.append(buf_line)

            return result

        new_lines = _renumber_lines(new_lines)

    try:
        new_content = '\n'.join(new_lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        wiki_path.write_text(new_content, encoding='utf-8')
        return True, old_topic
    except Exception as e:
        sys.stderr.write(f"[remove_file] write failed: {e}\n")
        sys.stderr.flush()
        return False, None


def move_file_to_topic(file_rel_path, new_topic, file_title=None):
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

    if add_success:
        if old_topic:
            return {"success": True, "message": f"已从「{old_topic}」移动到「{new_topic}」"}
        else:
            return {"success": True, "message": f"已添加到「{new_topic}」"}
    else:
        return {"success": False, "message": "移动失败"}
