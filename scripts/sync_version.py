"""Sync version from version.txt to tauri.conf.json and mcp-server."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PATH = ROOT / "version.txt"
TAURI_CONF_PATH = ROOT / "src-tauri" / "tauri.conf.json"
MCP_PACKAGE_PATH = ROOT / "mcp-server" / "package.json"
MCP_INDEX_PATH = ROOT / "mcp-server" / "src" / "index.js"


def main():
    version = VERSION_PATH.read_text(encoding="utf-8").strip()
    if not version:
        sys.exit("version.txt is empty")

    # 注意：pyproject.toml 版本与 uv.lock 绑定，且发布版本以 tauri.conf.json 为准，
    # 故此处只同步桌面应用与 mcp-server 的版本，不动 pyproject.toml / uv.lock。
    tauri_text = TAURI_CONF_PATH.read_text(encoding="utf-8")
    tauri_text = re.sub(r'^(\s*"version"):\s*"[^"]+"', rf'\1: "{version}"', tauri_text, flags=re.M)
    TAURI_CONF_PATH.write_text(tauri_text, encoding="utf-8")

    # mcp-server 为独立 npm 包，package.json 与 package-lock.json 需同步，否则 npm ci 失败
    mcp_pkg_text = MCP_PACKAGE_PATH.read_text(encoding="utf-8")
    mcp_pkg_text = re.sub(r'("version"\s*:\s*")[^"]+(")', rf"\g<1>{version}\g<2>", mcp_pkg_text, count=1)
    MCP_PACKAGE_PATH.write_text(mcp_pkg_text, encoding="utf-8")

    mcp_lock_path = MCP_PACKAGE_PATH.with_name("package-lock.json")
    if mcp_lock_path.exists():
        mcp_lock_text = mcp_lock_path.read_text(encoding="utf-8")
        mcp_lock_text = re.sub(r'("version"\s*:\s*")[^"]+(")', rf"\g<1>{version}\g<2>", mcp_lock_text, count=2)
        mcp_lock_path.write_text(mcp_lock_text, encoding="utf-8")

    # src/index.js 中 Server 构造时的硬编码版本：{ name: 'noteai-vault', version: '...' }
    mcp_index_text = MCP_INDEX_PATH.read_text(encoding="utf-8")
    new_mcp_index_text, n = re.subn(
        r"(name:\s*'noteai-vault',\s*version:\s*')[^']+(')", rf"\g<1>{version}\g<2>", mcp_index_text
    )
    if n != 1:
        sys.exit("failed to locate hardcoded version in mcp-server/src/index.js")
    MCP_INDEX_PATH.write_text(new_mcp_index_text, encoding="utf-8")

    print(f"Synced version {version}")


if __name__ == "__main__":
    main()
