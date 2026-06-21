"""Sync version from version.txt to pyproject.toml and tauri.conf.json."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PATH = ROOT / "version.txt"
PYPROJECT_PATH = ROOT / "pyproject.toml"
TAURI_CONF_PATH = ROOT / "src-tauri" / "tauri.conf.json"


def main():
    version = VERSION_PATH.read_text(encoding="utf-8").strip()
    if not version:
        sys.exit("version.txt is empty")

    pyproject_text = PYPROJECT_PATH.read_text(encoding="utf-8")
    pyproject_text = re.sub(r'^(version\s*=\s*")[^"]+(".*)$', rf'\g<1>{version}\g<2>', pyproject_text, flags=re.M)
    PYPROJECT_PATH.write_text(pyproject_text, encoding="utf-8")

    tauri_text = TAURI_CONF_PATH.read_text(encoding="utf-8")
    tauri_text = re.sub(r'^(\s*"version"):\s*"[^"]+"', rf'\1: "{version}"', tauri_text, flags=re.M)
    TAURI_CONF_PATH.write_text(tauri_text, encoding="utf-8")

    print(f"Synced version {version}")


if __name__ == "__main__":
    main()
