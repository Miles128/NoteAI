#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON_SIDECAR = ROOT / "python" / "sidecar"
RUST_RPC = ROOT / "src-tauri" / "src" / "rpc.rs"

REGISTER_RE = re.compile(r"""router\.register\(\s*["'](\w+)["']""")

RUST_ARRAY_RE = re.compile(
    r"static\s+ALLOWED_PYTHON_METHODS\s*:\s*&\[&str\]\s*=\s*&\[(.*?)\];",
    re.DOTALL,
)
RUST_METHOD_RE = re.compile(r'"(\w+)"')


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

    if not missing_in_rust and not stale_in_rust:
        print("OK: Rust whitelist is in sync with Python RPC registrations.")
        return 0

    merged = sorted(py_names)

    if args.fix:
        rust_text = RUST_RPC.read_text(encoding="utf-8")
        new_body = format_rust_array(merged)
        new_text = rust_text[:arr_start] + new_body + rust_text[arr_end:]
        RUST_RPC.write_text(new_text, encoding="utf-8")
        print(f"FIXED: Updated Rust whitelist ({len(merged)} methods).")
        return 0

    print("Run with --fix to auto-update the Rust whitelist.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
