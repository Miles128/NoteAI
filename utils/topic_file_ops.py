import re
import sys
from pathlib import Path

from config.constants import TOPIC_SEP
from config.settings import config
from utils.logger import logger
from utils.text_utils import parse_frontmatter
from utils.topic_classifier import _norm_topic


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


def _check_topic_needs_processing(meta) -> bool:
    if not meta:
        return True
    topic = meta.get('topic')
    if topic is None:
        return True
    if isinstance(topic, str):
        if not topic.strip():
            return True
    elif isinstance(topic, list):
        if len(topic) == 0 or len(topic) > 1:
            return True
    return False


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


def _optimize_file_format(full_path, text, meta=None, body=None):
    from utils.helpers import smart_format_markdown

    if body is None:
        body = text
    title = full_path.stem
    if meta:
        t = meta.get('title')
        if t and isinstance(t, str):
            title = t

    if not _needs_format_optimization(body):
        return False

    optimized_body = smart_format_markdown(body, title)
    if optimized_body == body:
        return False

    if meta:
        import yaml as _yaml
        fm_str = _yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
        new_content = '---\n' + fm_str + '\n---\n' + optimized_body
    else:
        new_content = optimized_body

    try:
        full_path.write_text(new_content, encoding='utf-8')
        return True
    except (OSError, ValueError) as e:
        sys.stderr.write(f"[topic_assigner] _optimize_file_format write failed: {e}\n")
        sys.stderr.flush()
        return False


def _remove_empty_dir(dir_path):
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
    from utils.wiki_manager import remove_file_from_wiki_topic, add_file_to_wiki_topic

    new_topic = _norm_topic(new_topic)
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    file_path = Path(workspace) / file_rel_path
    if not file_path.exists():
        return {"success": False, "message": f"文件不存在: {file_rel_path}"}

    if file_title is None:
        try:
            text = file_path.read_text(encoding='utf-8')
            meta, _ = parse_frontmatter(text)
            if meta:
                t = meta.get('title')
                if t and isinstance(t, str):
                    file_title = t
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
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        meta, _ = parse_frontmatter(text)
        if not meta:
            return None
        topic = meta.get('topic')
        if topic and isinstance(topic, str) and topic.strip():
            return _norm_topic(topic.strip())
        return None
    except Exception as e:
        sys.stderr.write(f"[_read_topic] failed: {e}\n")
        sys.stderr.flush()
        return None


def _read_title_from_file(file_path):
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        meta, _ = parse_frontmatter(text)
        if meta:
            t = meta.get('title')
            if t and isinstance(t, str) and t.strip():
                return t.strip()
        return Path(file_path).stem
    except Exception:
        return Path(file_path).stem
