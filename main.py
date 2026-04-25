#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NoteAI - AI驱动的Markdown笔记知识库管理桌面应用

功能模块：
1. 网络文章批量下载与转换
2. 多格式文件转换（PDF、PPT、DOCX、TXT）
3. LLM驱动的笔记主题整合

前端框架支持：
- PySide6 (优先): 使用 QtWebEngine，功能完整
- pywebview (备选): 使用系统 WebView，轻量
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

PYSIDE6_AVAILABLE = False
PYWEBVIEW_AVAILABLE = False

try:
    from PySide6.QtWidgets import QApplication
    PYSIDE6_AVAILABLE = True
    print("[INFO] PySide6 is available")
except ImportError:
    print("[INFO] PySide6 not available")

try:
    import webview
    PYWEBVIEW_AVAILABLE = True
    print("[INFO] pywebview is available")
except ImportError:
    print("[INFO] pywebview not available")


def check_dependencies(use_pyside6=True):
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
    ]

    if not use_pyside6:
        dependencies.append(("webview", "pywebview"))

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


def main_pyside6():
    """使用 PySide6 启动应用"""
    if not PYSIDE6_AVAILABLE:
        print("[ERROR] PySide6 is not installed")
        print("请安装: uv pip install PySide6")
        return False

    from webui.app_pyside6 import main as pyside6_main
    print("[INFO] Starting application with PySide6...")
    pyside6_main()
    return True


def main_pywebview():
    """使用 pywebview 启动应用"""
    if not PYWEBVIEW_AVAILABLE:
        print("[ERROR] pywebview is not installed")
        print("请安装: uv pip install pywebview")
        return False

    from webui.app import main as webview_main
    print("[INFO] Starting application with pywebview...")
    webview_main()
    return True


def main():
    """主函数 - 自动选择前端框架"""
    use_pyside6 = PYSIDE6_AVAILABLE

    if not check_dependencies(use_pyside6=use_pyside6):
        input("按Enter键退出...")
        return

    if use_pyside6:
        success = main_pyside6()
        if not success and PYWEBVIEW_AVAILABLE:
            print("\n[INFO] Falling back to pywebview...")
            main_pywebview()
    else:
        main_pywebview()


if __name__ == "__main__":
    main()
