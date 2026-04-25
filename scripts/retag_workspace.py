#!/usr/bin/env python3
import sys
import re
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.tag_extractor import (
    parse_yaml_frontmatter,
    generate_yaml_frontmatter,
    add_yaml_frontmatter_to_file,
    extract_tags_from_filename,
)

WORKSPACE = Path("/Users/sihai/Documents/My Notes")


def clear_old_tags(content: str) -> str:
    """清除旧式标签行和 YAML front matter 中的 tags/word_count/language 字段"""
    content = re.sub(r'\n*---\n\*标签:.*?\*\n*$', '', content)

    frontmatter, body = parse_yaml_frontmatter(content)

    if not frontmatter:
        return content

    for key in ['tags', 'word_count', 'language']:
        frontmatter.pop(key, None)

    source = frontmatter.pop('source', '')
    title = frontmatter.pop('title', '')
    date = frontmatter.pop('date', None)

    extra = {k: v for k, v in frontmatter.items() if k not in ('title', 'tags', 'date', 'source')}

    new_fm = generate_yaml_frontmatter(
        title=title,
        tags=[],
        date=date,
        source=source,
        extra_fields=extra if extra else None,
    )

    return new_fm + body


def main():
    md_files = [f for f in WORKSPACE.rglob('*.md') if not f.name.startswith('.')]

    print(f"找到 {len(md_files)} 个 MD 文件")
    print("=" * 60)

    cleared = 0
    retagged = 0

    for i, md_file in enumerate(md_files, 1):
        rel = md_file.relative_to(WORKSPACE)
        try:
            content = md_file.read_text(encoding='utf-8')
            cleaned = clear_old_tags(content)

            if cleaned != content:
                md_file.write_text(cleaned, encoding='utf-8')
                cleared += 1
                print(f"[{i}/{len(md_files)}] 清除旧标签: {rel}")
            else:
                print(f"[{i}/{len(md_files)}] 无旧标签: {rel}")

        except Exception as e:
            print(f"[{i}/{len(md_files)}] ✗ 清除失败 {rel}: {e}")

    print("\n" + "=" * 60)
    print(f"旧标签清除完成: {cleared}/{len(md_files)} 个文件被修改")
    print("=" * 60)
    print("\n开始用新方法重新生成标签...")

    for i, md_file in enumerate(md_files, 1):
        rel = md_file.relative_to(WORKSPACE)
        try:
            tags = extract_tags_from_filename(str(md_file))
            if tags:
                add_yaml_frontmatter_to_file(str(md_file), tags=tags)
                retagged += 1
                print(f"[{i}/{len(md_files)}] ✓ {rel} → tags: {tags}")
            else:
                print(f"[{i}/{len(md_files)}] - {rel} → 无标签")
        except Exception as e:
            print(f"[{i}/{len(md_files)}] ✗ 生成失败 {rel}: {e}")

    print("\n" + "=" * 60)
    print(f"标签重新生成完成: {retagged}/{len(md_files)} 个文件获得标签")
    print("=" * 60)


if __name__ == '__main__':
    main()
