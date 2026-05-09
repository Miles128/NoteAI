import os, re, yaml
from pathlib import Path
from datetime import datetime

workspace = Path('/Users/sihai/Documents/My Notes')
notes_dir = workspace / 'Notes'

topic_map = {}
topic_files = {}

for subfolder in sorted(notes_dir.iterdir()):
    if not subfolder.is_dir() or subfolder.name.startswith('.'):
        continue
    topic_name = subfolder.name
    topic_files[topic_name] = []
    for md_file in sorted(subfolder.glob('*.md')):
        if not md_file.name.startswith('.'):
            topic_map[md_file] = topic_name
            topic_files[topic_name].append(md_file.name)

def extract_frontmatter_and_body(text):
    text = text.lstrip('\ufeff')
    fm_parts = []
    body = text
    while body.startswith('---'):
        end = body.find('\n---', 4)
        if end < 0:
            break
        chunk = body[4:end].strip()
        if chunk:
            fm_parts.append(chunk)
        body = body[end + 4:]
        if body.startswith('\n'):
            body = body[1:]
        body = body.lstrip('\ufeff')
    return fm_parts, body

def clean_fm_text(fm_text):
    lines = fm_text.split('\n')
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith('topic:') or stripped.startswith('topics:'):
            i += 1
            while i < len(lines):
                next_stripped = lines[i].lstrip()
                if next_stripped.startswith('- ') or next_stripped.startswith('  ') or next_stripped.startswith('\t'):
                    i += 1
                else:
                    break
            continue
        if stripped.startswith('- ') and (not cleaned or not cleaned[-1].strip()):
            i += 1
            continue
        cleaned.append(line)
        i += 1
    return '\n'.join(cleaned)

updated = 0
for md_file, topic_name in topic_map.items():
    try:
        text = md_file.read_text(encoding='utf-8')
        fm_parts, body = extract_frontmatter_and_body(text)

        merged_fm = '\n'.join(fm_parts)
        merged_fm = clean_fm_text(merged_fm)
        merged_fm = re.sub(r'\n{3,}', '\n\n', merged_fm)
        merged_fm = merged_fm.strip()
        if merged_fm:
            merged_fm += f'\ntopics:\n- {topic_name}'
        else:
            merged_fm = f'topics:\n- {topic_name}'

        new_content = f'---\n{merged_fm}\n---\n{body}'
        md_file.write_text(new_content, encoding='utf-8')
        updated += 1
    except Exception as e:
        print(f'Error: {md_file.name}: {e}')

print(f'Updated {updated} files')

wiki_lines = ['# WIKI\n']
wiki_lines.append(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
wiki_lines.append(f'主题数量: {len(topic_files)}\n')
wiki_lines.append('## 目录\n')
for topic_name in sorted(topic_files.keys()):
    count = len(topic_files[topic_name])
    wiki_lines.append(f'- {topic_name} - {count} 个文件')
wiki_lines.append('')
for topic_name in sorted(topic_files.keys()):
    wiki_lines.append(f'## {topic_name}\n')
    wiki_lines.append('### 来源文件\n')
    for i, fname in enumerate(topic_files[topic_name], 1):
        wiki_lines.append(f'{i}. **{fname.replace(".md", "")}**')
        wiki_lines.append(f'   - 文件名：{fname}')
        wiki_lines.append(f'   - 原始路径：Notes/{topic_name}/{fname}')
    wiki_lines.append('')

wiki_path = workspace / 'WIKI.md'
wiki_path.write_text('\n'.join(wiki_lines), encoding='utf-8')
print(f'WIKI.md rewritten with {len(topic_files)} topics')
