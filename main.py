#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NoteAI - AI驱动的Markdown笔记知识库管理桌面应用

功能模块：
1. 网络文章批量下载与转换
2. 多格式文件转换（PDF、PPT、DOCX、TXT）
3. LLM驱动的笔记主题整合

前端框架：Tauri + HTML/CSS/JS
后端：Python sidecar (python/main.py)
"""

import sys
import subprocess
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def check_dependencies():
    dependencies = [
        ("langchain_openai", "langchain-openai"),
        ("langchain_core", "langchain-core"),
        ("requests", "requests"),
        ("bs4", "beautifulsoup4"),
        ("readability", "readability-lxml"),
        ("docx", "python-docx"),
        ("fitz", "PyMuPDF"),
        ("mammoth", "mammoth"),
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
        print(f"uv pip install {' '.join(missing)}")
        return False

    return True


def check_tauri_cli():
    try:
        result = subprocess.run(
            ["cargo", "tauri", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    try:
        result = subprocess.run(
            ["npx", "tauri", "--version"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print("未找到 Tauri CLI，请先安装：")
    print("  cargo install tauri-cli")
    print("  或 npm install -g @tauri-apps/cli")
    return False


def main():
    if not check_dependencies():
        input("按Enter键退出...")
        return

    if not check_tauri_cli():
        input("按Enter键退出...")
        return

    src_tauri = project_root / "src-tauri"
    print("[INFO] 启动 Tauri 开发模式...")
    try:
        subprocess.run(
            ["cargo", "tauri", "dev"],
            cwd=str(src_tauri),
        )
    except KeyboardInterrupt:
        print("\n[INFO] 应用已关闭")
    except FileNotFoundError:
        try:
            subprocess.run(
                ["npx", "tauri", "dev"],
                cwd=str(src_tauri),
            )
        except KeyboardInterrupt:
            print("\n[INFO] 应用已关闭")


if __name__ == "__main__":
    main()
