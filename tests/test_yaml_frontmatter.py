#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试YAML front matter生成功能"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.tag_extractor import (
    generate_yaml_frontmatter,
    add_yaml_frontmatter_to_content,
    parse_yaml_frontmatter,
    extract_tags_from_filename,
    split_filename_fields
)


def test_generate_frontmatter():
    """测试生成YAML front matter"""
    print("=" * 60)
    print("测试1: 生成基本YAML front matter")
    print("=" * 60)

    frontmatter = generate_yaml_frontmatter(
        title='测试文档标题',
        tags=['人工智能', '机器学习', '深度学习'],
        source='https://example.com/article'
    )
    print(frontmatter)
    assert frontmatter.startswith('---')
    assert 'title:' in frontmatter
    assert 'tags:' in frontmatter
    assert '人工智能' in frontmatter
    print("✓ 通过\n")


def test_special_characters():
    """测试特殊字符处理"""
    print("=" * 60)
    print("测试2: 特殊字符处理")
    print("=" * 60)

    frontmatter = generate_yaml_frontmatter(
        title='测试: 包含"引号"和: 冒号的标题',
        tags=['tag1', 'tag2'],
        source='C:\\Users\\test\\file.pdf'
    )
    print(frontmatter)
    assert frontmatter.startswith('---')
    print("✓ 通过\n")


def test_add_frontmatter_to_content():
    """测试添加front matter到内容"""
    print("=" * 60)
    print("测试3: 添加front matter到内容")
    print("=" * 60)

    content = '''# 测试标题

这是一段测试内容。包含中文和英文混合。

人工智能、机器学习、深度学习是当前热门技术。

## 第二章节

更多内容...
'''
    result = add_yaml_frontmatter_to_content(
        content,
        title='自动提取标题测试',
        source='test.md'
    )
    print(result)
    assert result.startswith('---')
    assert '# 测试标题' in result
    print("✓ 通过\n")


def test_split_filename_fields():
    """测试文件名字段拆分"""
    print("=" * 60)
    print("测试4: 文件名字段拆分")
    print("=" * 60)

    cases = [
        ("机器学习-神经网络-反向传播.md", ["机器学习", "神经网络", "反向传播"]),
        ("Python_基础教程.md", ["Python", "基础教程"]),
        ("React Hooks 详解.md", ["React", "Hooks", "详解"]),
        ("设计模式——观察者模式.md", ["设计模式", "观察者模式"]),
    ]
    for filename, expected in cases:
        fields = split_filename_fields(filename)
        print(f"  {filename} → {fields}")
        assert fields == expected, f"期望 {expected}, 得到 {fields}"
    print("✓ 通过\n")


def test_parse_frontmatter():
    """测试解析front matter"""
    print("=" * 60)
    print("测试5: 解析YAML front matter")
    print("=" * 60)

    full_content = '''---
title: "测试文档"
tags: [tag1, tag2, tag3]
date: "2026-04-19"
source: "https://example.com"
---

# 正文标题

正文内容...
'''
    try:
        frontmatter_dict, body = parse_yaml_frontmatter(full_content)
        print(f"解析的front matter: {frontmatter_dict}")
        print(f"正文: {body[:50]}...")
        assert frontmatter_dict.get('title') == '测试文档'
        assert '# 正文标题' in body
        print("✓ 通过\n")
    except ImportError:
        print("⚠ PyYAML未安装，跳过解析测试（不影响生成功能）\n")


def test_empty_content():
    """测试空内容边界情况"""
    print("=" * 60)
    print("测试6: 边界情况 - 空内容")
    print("=" * 60)

    frontmatter = generate_yaml_frontmatter()
    print(frontmatter)
    assert frontmatter.startswith('---')
    print("✓ 通过\n")


def main():
    print("\n" + "=" * 60)
    print("YAML Front Matter 功能测试")
    print("=" * 60 + "\n")

    try:
        test_generate_frontmatter()
        test_special_characters()
        test_add_frontmatter_to_content()
        test_split_filename_fields()
        test_parse_frontmatter()
        test_empty_content()

        print("=" * 60)
        print("所有测试通过！")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
