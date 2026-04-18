#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NoteAI - AI驱动的Markdown笔记知识库管理桌面应用

功能模块：
1. 网络文章批量下载与转换
2. 多格式文件转换（PDF、PPT、DOCX、TXT）
3. LLM驱动的笔记主题整合
   - 阶段1: 按Heading拆分文档为文本块
   - 阶段2: LLM提取主题与块归属映射
   - 阶段3: 按主题拼接内容并生成笔记
   - 阶段4: 格式化输出为独立Markdown文件
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
        ("webview", "pywebview"),
        ("markdown", "markdown"),
        ("validators", "validators"),
        ("pydantic", "pydantic"),
        ("tiktoken", "tiktoken"),
        ("markdownify", "markdownify"),
    ]
    missing = []
    for module_name, package_name in dependencies:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)

    if missing:
        print("缺少以下依赖包，请先安装：")
        print(f"pip install {' '.join(missing)}")
        return False

    return True


def main():
    """主函数"""
    if not check_dependencies():
        input("按Enter键退出...")
        return

    from webui.app import main as webview_main
    webview_main()


if __name__ == "__main__":
    main()
