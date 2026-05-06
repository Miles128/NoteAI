import re
import pathlib

workspace = pathlib.Path('/Users/sihai/Documents/My Notes')
updated = 0
skipped = 0

for f in sorted(workspace.rglob('*.md')):
    if f.name.startswith('.') or f.name.lower() in ('wiki.md', 'tags.md', 'wiki.md'):
        continue

    rel = f.relative_to(workspace)
    parts = rel.parts
    if len(parts) < 2:
        skipped += 1
        continue

    folder_name = parts[-2]

    try:
        text = f.read_text(encoding='utf-8')
        m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)

        if m:
            fm = m.group(1)
            body = text[m.end():]
            if re.search(r'^topic:', fm, re.MULTILINE):
                fm = re.sub(r'^topic:.*$', 'topic: ' + folder_name, fm, flags=re.MULTILINE)
            else:
                fm += '\ntopic: ' + folder_name
            new_text = '---\n' + fm + '\n---' + body
        else:
            new_text = '---\ntopic: ' + folder_name + '\n---\n' + text

        f.write_text(new_text, encoding='utf-8')
        updated += 1
    except Exception as e:
        print(f'ERROR: {f}: {e}')

print(f'Updated: {updated}, Skipped (root level): {skipped}')
