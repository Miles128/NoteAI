import re, sys, shutil
from pathlib import Path

workspace = Path('/Users/sihai/Documents/My Notes')
notes_dir = workspace / 'Notes'

moved = 0
skipped = 0
errors = 0

def get_topic(md_file):
    try:
        text = md_file.read_text(encoding='utf-8')
    except:
        return None
    m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
    if not m:
        return None
    for line in m.group(1).split('\n'):
        idx = line.find(':')
        if idx < 0:
            continue
        key = line[:idx].strip()
        val = line[idx+1:].strip().strip("'\"")
        if key == 'topic' and val:
            return val
    return None

def move_to_topic(md_file, topic):
    global moved, errors
    safe_topic = topic.replace('..', '').strip('/')
    topic_dir = notes_dir / safe_topic
    topic_dir.mkdir(parents=True, exist_ok=True)
    dst = topic_dir / md_file.name

    if dst.exists() and dst.resolve() != md_file.resolve():
        stem = md_file.stem
        suffix = md_file.suffix
        counter = 1
        while dst.exists():
            dst = topic_dir / f'{stem}_{counter}{suffix}'
            counter += 1

    if dst.resolve() == md_file.resolve():
        return

    try:
        shutil.move(str(md_file), str(dst))
        moved += 1
        print(f'移动: {md_file.name} -> Notes/{safe_topic}/')
    except Exception as e:
        errors += 1
        print(f'错误: {md_file.name} -> {e}')

for md_file in list(notes_dir.glob('*.md')):
    topic = get_topic(md_file)
    if not topic:
        skipped += 1
        continue
    move_to_topic(md_file, topic)

for md_file in workspace.glob('*.md'):
    if md_file.name.startswith('.') or md_file.name.lower() in ('wiki.md', 'tags.md', 'readme.md'):
        continue
    topic = get_topic(md_file)
    if not topic:
        continue
    move_to_topic(md_file, topic)

print(f'\n总计: 移动 {moved}, 跳过(无主题) {skipped}, 错误 {errors}')
