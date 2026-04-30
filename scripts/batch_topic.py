#!/usr/bin/env python3
import sys
from pathlib import Path

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from config.settings import config, is_ignored_dir
from utils.topic_assigner import auto_assign_topic_for_file, load_pending, parse_wiki_headings
import os
import re


def main():
    workspace = config.workspace_path
    if not workspace:
        print("错误: 未设置工作区路径")
        return

    ws = Path(workspace)
    if not ws.exists():
        print(f"错误: 工作区不存在: {workspace}")
        return

    headings = parse_wiki_headings()
    h_names = [h["name"] for h in headings]
    print(f"工作区: {workspace}")
    print(f"WIKI 主题数: {len(headings)}")
    if h_names:
        print(f"主题列表: {', '.join(h_names[:10])}{'...' if len(h_names) > 10 else ''}")
    print("-" * 50)

    total = 0
    skipped = 0
    assigned = 0

    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not is_ignored_dir(d)]
        for fname in sorted(files):
            if not fname.endswith('.md'):
                continue
            fpath = Path(root) / fname
            total += 1
            try:
                text = fpath.read_text(encoding='utf-8')
            except Exception:
                skipped += 1
                continue

            has_topic = False
            m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
            if m:
                for line in m.group(1).split('\n'):
                    idx = line.find(':')
                    if idx > 0 and line[:idx].strip() == 'topic':
                        has_topic = True
                        break

            if has_topic:
                continue

            rel = str(fpath.relative_to(ws))
            try:
                auto_assign_topic_for_file(str(fpath))
                assigned += 1
                if total % 20 == 0:
                    print(f"  已处理 {total} 个文件...")
            except Exception as e:
                print(f"  失败: {rel} - {e}")

    pending = load_pending()
    pending_count = len(pending)

    print("-" * 50)
    print(f"扫描完成:")
    print(f"  总计 MD 文件: {total}")
    print(f"  跳过 (读取失败): {skipped}")
    print(f"  已有主题: {total - assigned - skipped}")
    print(f"  新处理: {assigned}")
    print(f"  待确认: {pending_count}")
    print("")
    print("重启 NoteAI 应用后，点击「主题」按钮查看结果")


if __name__ == '__main__':
    main()
