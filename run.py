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
    """从 pyproject.toml 读取依赖列表并检查是否已安装"""
    proj_root = Path(__file__).parent
    toml_path = proj_root / "pyproject.toml"
    if not toml_path.exists():
        print("未找到 pyproject.toml，跳过依赖检查")
        return True

    # 尝试用 tomllib (Python 3.11+) 或 tomli 解析
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            print("未安装 tomllib/tomli，跳过依赖检查")
            print("请手动执行: uv sync")
            return True

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        print("解析 pyproject.toml 失败，跳过依赖检查")
        return True

    dependencies = data.get("project", {}).get("dependencies", [])
    if not dependencies:
        print("pyproject.toml 中未找到依赖列表")
        return True

    # 解析包名：从 "pkg>=1.0" 或 "pkg[extra]>=1.0" 等格式中提取包名
    import re
    missing = []
    for dep_str in dependencies:
        dep_str = dep_str.strip()
        if not dep_str or dep_str.startswith("#"):
            continue
        # 提取包名（去掉版本约束和 extras）
        pkg_name = re.split(r'[<>=!~;\[]', dep_str)[0].strip()
        # 映射 PyPI 包名到 import 模块名
        import_name = pkg_name.replace("-", "_")
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg_name)

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
