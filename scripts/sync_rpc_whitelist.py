#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON_SIDECAR = ROOT / "python" / "sidecar"
RUST_RPC = ROOT / "src-tauri" / "src" / "rpc.rs"
WEBUI_JS = ROOT / "webui" / "js"
API_JS = WEBUI_JS / "api.js"

REGISTER_RE = re.compile(r"""router\.register\(\s*["'](\w+)["']""")

RUST_ARRAY_RE = re.compile(
    r"static\s+ALLOWED_PYTHON_METHODS\s*:\s*&\[&str\]\s*=\s*&\[(.*?)\];",
    re.DOTALL,
)
RUST_METHOD_RE = re.compile(r'"(\w+)"')

# api.js 中的配置化定义：{ name: 'xxx', method: 'yyy', ... }
API_DEF_RE = re.compile(r"name:\s*'(\w+)'\s*,\s*method:\s*'(\w+)'")
# api.js 特殊函数中的直调 pyCall（多步逻辑 / 原生对话框 / 分页预览，无法配置化）
PYCALL_DIRECT_RE = re.compile(r"pyCall\('(\w+)'")
# 其他前端文件中绕过 API_DEFS 的裸调用：window.api.invoke('method', ...)
BARE_INVOKE_RE = re.compile(r"api\.invoke\(\s*'(\w+)'")

# 已注册于 Python / Rust 白名单，但仅供后端内部或其他客户端使用、
# 前端刻意不暴露的方法（新增此类方法时在此登记并注明原因）。
KNOWN_BACKEND_ONLY_METHODS = {
    "append_chat_to_survey",  # 综述归档内部链路
    "delete_topic_safe",  # 3 层主题树内部使用
    "get_survey_status",  # 综述轮询内部使用
    "get_topic_tree_3tier",  # 3 层主题树内部使用
    "rag_retrieval_debug",  # 检索透明化面板，前端 P9 任务对接后移出
    "retry_semantic_failed_blocks",  # 语义编译重试内部使用
    "set_abstract_config",  # 3 层主题树内部使用
}


def scan_python_methods():
    methods = {}
    search_dirs = [
        PYTHON_SIDECAR / "handlers",
        PYTHON_SIDECAR / "mixins",
    ]
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for py_file in sorted(search_dir.rglob("*.py")):
            text = py_file.read_text(encoding="utf-8")
            for m in REGISTER_RE.finditer(text):
                method_name = m.group(1)
                rel = py_file.relative_to(ROOT)
                methods[method_name] = str(rel)
    return methods


def read_rust_whitelist():
    text = RUST_RPC.read_text(encoding="utf-8")
    m = RUST_ARRAY_RE.search(text)
    if not m:
        print("ERROR: cannot find ALLOWED_PYTHON_METHODS in rpc.rs", file=sys.stderr)
        sys.exit(2)
    methods = RUST_METHOD_RE.findall(m.group(1))
    return set(methods), m.start(1), m.end(1)


def format_rust_array(methods_sorted):
    lines = []
    for name in methods_sorted:
        lines.append(f'    "{name}",')
    return "\n" + "\n".join(lines) + "\n"


def check_frontend_consistency(rust_names, py_names):
    """交叉校验 webui/js/api.js 与 Rust 白名单（只读，返回是否有漂移）。"""
    api_text = API_JS.read_text(encoding="utf-8")

    api_defs = dict(API_DEF_RE.findall(api_text))  # name -> method
    pycall_direct = set(PYCALL_DIRECT_RE.findall(api_text))
    frontend_methods = set(api_defs.values()) | pycall_direct

    # 其他前端文件中绕过 API_DEFS 的裸 api.invoke('method', ...) 调用
    bare_invokes = []
    for js_file in sorted(WEBUI_JS.glob("*.js")):
        if js_file == API_JS:
            continue
        for m in BARE_INVOKE_RE.finditer(js_file.read_text(encoding="utf-8")):
            bare_invokes.append((str(js_file.relative_to(ROOT)), m.group(1)))

    ok = True

    api_only = sorted(frontend_methods - rust_names)
    if api_only:
        ok = False
        print("=== api.js methods MISSING from Rust whitelist (would be BLOCKED) ===")
        for name in api_only:
            print(f"  + {name}")
        print()

    rust_only = sorted(rust_names - frontend_methods - KNOWN_BACKEND_ONLY_METHODS)
    if rust_only:
        ok = False
        print("=== Rust whitelist methods NOT exposed in api.js (DRIFT) ===")
        for name in rust_only:
            registered = name in py_names
            hint = "" if registered else "  (also NOT registered in Python)"
            print(f"  - {name}{hint}")
        print()

    unknown_exempt = sorted(KNOWN_BACKEND_ONLY_METHODS - rust_names)
    if unknown_exempt:
        ok = False
        print("=== KNOWN_BACKEND_ONLY_METHODS entries absent from Rust whitelist (STALE) ===")
        for name in unknown_exempt:
            print(f"  - {name}")
        print()

    if bare_invokes:
        ok = False
        print("=== Bare api.invoke() calls bypassing API_DEFS ===")
        for rel_path, method in bare_invokes:
            print(f"  - {rel_path}: {method}")
        print()

    if ok:
        print(
            f"OK: api.js is consistent with Rust whitelist "
            f"({len(frontend_methods)} frontend methods, "
            f"{len(KNOWN_BACKEND_ONLY_METHODS)} known backend-only)."
        )
    return ok


def main():
    parser = argparse.ArgumentParser(description="Sync RPC whitelist between Python and Rust")
    parser.add_argument("--fix", action="store_true", help="Auto-update Rust whitelist")
    args = parser.parse_args()

    py_methods = scan_python_methods()
    py_names = set(py_methods.keys())

    rust_names, arr_start, arr_end = read_rust_whitelist()

    missing_in_rust = sorted(py_names - rust_names)
    stale_in_rust = sorted(rust_names - py_names)

    if missing_in_rust:
        print("=== Python methods MISSING from Rust whitelist (would be BLOCKED) ===")
        for name in missing_in_rust:
            print(f"  + {name}  (from {py_methods[name]})")
        print()

    if stale_in_rust:
        print("=== Rust whitelist methods NOT registered in Python (STALE) ===")
        for name in stale_in_rust:
            print(f"  - {name}")
        print()

    frontend_ok = check_frontend_consistency(rust_names, py_names)

    if not missing_in_rust and not stale_in_rust and frontend_ok:
        print("OK: Rust whitelist is in sync with Python RPC registrations.")
        return 0

    merged = sorted(py_names)

    if args.fix:
        rust_text = RUST_RPC.read_text(encoding="utf-8")
        new_body = format_rust_array(merged)
        new_text = rust_text[:arr_start] + new_body + rust_text[arr_end:]
        RUST_RPC.write_text(new_text, encoding="utf-8")
        print(f"FIXED: Updated Rust whitelist ({len(merged)} methods).")
        # --fix 只同步 Python↔Rust；前端漂移需要手工修复 api.js
        return 0 if frontend_ok else 1

    print("Run with --fix to auto-update the Rust whitelist.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
