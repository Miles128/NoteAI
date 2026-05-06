import re
import pathlib

workspace = pathlib.Path('/Users/sihai/Documents/My Notes')
updated = 0
skipped = 0

for f in sorted(workspace.rglob('*.md')):
    if f.name.startswith('.') or f.name.lower() in ('wiki.md', 'tags.md'):
        continue

    stem = f.stem

    try:
        text = f.read_text(encoding='utf-8')
        m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)

        if m:
            body = text[m.end():]
            body = body.lstrip('\n')
            if re.match(r'^#\s+', body):
                body = re.sub(r'^#\s+.*', '# ' + stem, body, count=1)
            else:
                body = '# ' + stem + '\n\n' + body
            new_text = text[:m.end()] + '\n' + body
        else:
            if re.match(r'^#\s+', text):
                new_text = re.sub(r'^#\s+.*', '# ' + stem, text, count=1)
            else:
                new_text = '# ' + stem + '\n\n' + text

        f.write_text(new_text, encoding='utf-8')
        updated += 1
    except Exception as e:
        print(f'ERROR: {f}: {e}')

print(f'Updated: {updated}, Skipped: {skipped}')
