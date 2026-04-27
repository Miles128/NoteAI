#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NoteAI - AI驱动的Markdown笔记知识库管理桌面应用

功能模块：
1. 网络文章批量下载与转换
2. 多格式文件转换（PDF、PPT、DOCX、TXT）
3. LLM驱动的笔记主题整合

前端框架：
- PySide6 + QtWebEngine
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def check_dependencies():
    """检查依赖项"""
    dependencies = [
        ("langchain", "langchain"),
        ("langchain_openai", "langchain-openai"),
        ("langchain_community", "langchain-community"),
        ("requests", "requests"),
        ("bs4", "beautifulsoup4"),
        ("readability", "readability-lxml"),
        ("docx", "python-docx"),
        ("fitz", "PyMuPDF"),
        ("mammoth", "mammoth"),
        ("markdown", "markdown"),
        ("validators", "validators"),
        ("pydantic", "pydantic"),
        ("tiktoken", "tiktoken"),
        ("markdownify", "markdownify"),
        ("PySide6.QtWidgets", "PySide6"),
    ]

    missing = []
    for module_name, package_name in dependencies:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)

    if missing:
        print("缺少以下依赖包，请先安装：")
        print(f"uv pip install {' '.join(missing)}")
        return False

    return True


def main():
    """主函数"""
    if not check_dependencies():
        input("按Enter键退出...")
        return

    from webui.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
