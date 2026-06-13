import pathlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config

workspace = config.workspace_path
if not workspace:
    print("Error: 未设置工作区路径 (workspace_path)")
    exit(1)
workspace = pathlib.Path(workspace)
updated = 0
skipped = 0

for f in sorted(workspace.rglob("*.md")):
    if f.name.startswith(".") or "wiki" in f.parts:
        continue

    rel = f.relative_to(workspace)
    parts = rel.parts
    if len(parts) < 2:
        skipped += 1
        continue

    folder_name = parts[-2]

    try:
        text = f.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)

        if m:
            fm = m.group(1)
            body = text[m.end() :]
            if re.search(r"^topic:", fm, re.MULTILINE):
                fm = re.sub(r"^topic:.*$", "topic: " + folder_name, fm, flags=re.MULTILINE)
            else:
                fm += "\ntopic: " + folder_name
            new_text = "---\n" + fm + "\n---" + body
        else:
            new_text = "---\ntopic: " + folder_name + "\n---\n" + text

        f.write_text(new_text, encoding="utf-8")
        updated += 1
    except Exception as e:
        print(f"ERROR: {f}: {e}")

print(f"Updated: {updated}, Skipped (root level): {skipped}")
