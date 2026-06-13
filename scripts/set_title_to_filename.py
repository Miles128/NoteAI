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

    stem = f.stem

    try:
        text = f.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)

        if m:
            body = text[m.end() :]
            body = body.lstrip("\n")
            if re.match(r"^#\s+", body):
                body = re.sub(r"^#\s+.*", "# " + stem, body, count=1)
            else:
                body = "# " + stem + "\n\n" + body
            new_text = text[: m.end()] + "\n" + body
        elif re.match(r"^#\s+", text):
            new_text = re.sub(r"^#\s+.*", "# " + stem, text, count=1)
        else:
            new_text = "# " + stem + "\n\n" + text

        f.write_text(new_text, encoding="utf-8")
        updated += 1
    except Exception as e:
        print(f"ERROR: {f}: {e}")

print(f"Updated: {updated}, Skipped: {skipped}")
