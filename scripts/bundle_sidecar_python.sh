#!/usr/bin/env bash
# Copy project .venv into src-tauri/resources/sidecar-python for release bundles.
# Run before: cargo tauri build
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/.venv"
DEST="$ROOT/src-tauri/resources/sidecar-python"

if [[ ! -x "$SRC/bin/python3" && ! -x "$SRC/bin/python" ]]; then
  echo "Missing $SRC — run: uv sync" >&2
  exit 1
fi

echo "Bundling sidecar Python: $SRC -> $DEST"
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -R "$SRC" "$DEST"
echo "Done. Rebuild with: cargo tauri build"
