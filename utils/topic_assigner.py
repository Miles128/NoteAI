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
