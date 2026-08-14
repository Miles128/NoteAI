"""一次性迁移：将 YAML topic 中的 / 分隔符替换为  > 。
同时重建 WIKI.md 中每个 topic 名称的路径表示。
"""

import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config
from config.constants import TOPIC_SEP
from utils.logger import logger


def migrate_file_yaml(file_path: Path) -> bool:
    """将单个文件 YAML 中的 topic: 'A/B' 改为 topic: 'A > B'"""
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return False

    bom = "﻿" if text.startswith("﻿") else ""
    clean = text.lstrip("﻿")
    m = re.match(r"^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)", clean)
    if not m:
        return False

    yaml_text = m.group(2)
    lines = yaml_text.split("\n")
    changed = False
    new_lines = []

    for line in lines:
        idx = line.find(":")
        if idx < 0:
            new_lines.append(line)
            continue
        key = line[:idx].strip()
        if key == "topic":
            val = line[idx + 1 :].strip()
            # Only migrate if value contains / but not  >
            if "/" in val and TOPIC_SEP not in val:
                # Handle quoted YAML values
                val_clean = val.strip().strip("'\"")
                new_val = val_clean.replace("/", TOPIC_SEP)
                # Preserve quoting style
                if val.startswith("'") and val.endswith("'"):
                    line = f"topic: '{new_val}'"
                elif val.startswith('"') and val.endswith('"'):
                    line = f'topic: "{new_val}"'
                else:
                    line = f"topic: {new_val}"
                changed = True
        new_lines.append(line)

    if not changed:
        return False

    new_yaml = "\n".join(new_lines)
    new_text = bom + m.group(1) + new_yaml + m.group(3) + clean[m.end() :]
    try:
        file_path.write_text(new_text, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"迁移写入失败: {file_path} - {e}")
        return False


def main():
    workspace = config.workspace_path
    if not workspace:
        print("未设置工作区")
        return

    ws = Path(workspace)
    md_files = list(ws.rglob("*.md"))
    migrated = 0
    skipped = 0

    for f in md_files:
        if f.name == "WIKI.md":
            continue
        if migrate_file_yaml(f):
            migrated += 1
            print(f"  迁移: {f.relative_to(ws)}")
        else:
            skipped += 1

    print(f"\n完成: 迁移 {migrated} 个文件, 跳过 {skipped} 个 (无需迁移或失败)")


if __name__ == "__main__":
    main()
