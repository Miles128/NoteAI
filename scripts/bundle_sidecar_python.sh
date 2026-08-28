#!/usr/bin/env bash
# Stage slim Python packages for the Tauri resource bundle.
# Do NOT copy .venv (~1.4G). Runtime: NOTEAI_PYTHON, nearby .venv, or system python3.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$ROOT/src-tauri/resources/release"
FAT_VENV="$ROOT/src-tauri/resources/sidecar-python"

if [[ -e "$FAT_VENV" ]]; then
  echo "Removing stale $FAT_VENV"
  rm -rf "$FAT_VENV"
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"

copy_py() {
  local name="$1"
  rsync -a \
    --exclude '__pycache__/' \
    --exclude '*.py[cod]' \
    --exclude '.DS_Store' \
    --exclude '*.so' \
    "$ROOT/$name/" "$STAGE/$name/"
}

echo "Staging Python packages (no __pycache__)"
copy_py python
copy_py config
copy_py modules
copy_py prompts
copy_py utils

echo "Staged $(du -sh "$STAGE" | awk '{print $1}') at $STAGE"
