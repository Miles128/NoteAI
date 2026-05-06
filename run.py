#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NoteAI — 开发者启动器（v2）

检查依赖后启动 `cargo tauri dev`。应用本身由 Tauri 壳加载 webui/，
Python sidecar（`python/main.py`）通过 stdin/stdout JSON-RPC 提供后端服务。

不要与 `python/main.py`（sidecar 进程入口）混淆。
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
        ("yaml", "PyYAML"),
        ("markdown", "markdown"),
        ("jieba", "jieba"),
        ("PIL", "pillow"),
        ("html2text", "html2text"),
        ("watchdog", "watchdog"),
    ]

    missing = []
    for module_name, package_name in dependencies:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)

    if missing:
        print("缺少以下依赖包，请先安装：")
        print(f"  uv sync")
        print(f"  （或 pip install {' '.join(missing)}）")
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

    print("[INFO] 启动 Tauri 开发模式...")
    try:
        subprocess.run(
            ["cargo", "tauri", "dev"],
            cwd=str(project_root),
        )
    except KeyboardInterrupt:
        print("\n[INFO] 应用已关闭")
    except FileNotFoundError:
        try:
            subprocess.run(
                ["npx", "tauri", "dev"],
                cwd=str(project_root),
            )
        except KeyboardInterrupt:
            print("\n[INFO] 应用已关闭")


if __name__ == "__main__":
    main()
