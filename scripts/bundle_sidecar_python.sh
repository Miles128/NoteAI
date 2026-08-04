#!/usr/bin/env bash
# Copy project .venv into src-tauri/resources/sidecar-python for release bundles.
# Run before: cargo tauri build
#
# The interpreter is made self-contained: uv venvs symlink into the uv-managed
# Python installation, which would break inside an app bundle. We copy the real
# framework binary into the bundle and point the bin symlinks + pyvenv.cfg at it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/.venv"
DEST="$ROOT/src-tauri/resources/sidecar-python"

if [[ ! -e "$SRC/bin/python3" && ! -e "$SRC/bin/python" ]]; then
  echo "Missing $SRC — run: uv sync" >&2
  exit 1
fi

echo "Bundling sidecar Python: $SRC -> $DEST"
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
cp -R "$SRC" "$DEST"

# Resolve the interpreter symlink to the real uv-managed binary.
REAL_PY="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$DEST/bin/python3" 2>/dev/null || true)"
if [[ -z "$REAL_PY" || ! -x "$REAL_PY" ]]; then
  echo "Warning: could not resolve $DEST/bin/python3 — bundle may rely on system Python" >&2
  exit 0
fi

if [[ "$(uname)" == "Darwin" ]]; then
  # uv venvs only contain site-packages; the stdlib and dylibs live in the
  # uv-managed standalone build. Merge them in so the bundle is self-contained
  # (standalone builds are relocatable via @executable_path-relative rpaths).
  BASE="$(cd "$(dirname "$REAL_PY")/.." && pwd)"
  for item in "$BASE/lib/"*; do
    name="$(basename "$item")"
    if [[ -d "$DEST/lib/$name" ]]; then
      cp -R "$item/" "$DEST/lib/$name/"
    else
      cp -R "$item" "$DEST/lib/"
    fi
  done
  rm -f "$DEST/bin/python" "$DEST/bin/python3" "$DEST/bin/python3."*
  cp "$REAL_PY" "$DEST/bin/$(basename "$REAL_PY")"
  chmod +x "$DEST/bin/$(basename "$REAL_PY")"
  ln -s "$(basename "$REAL_PY")" "$DEST/bin/python3"
  ln -s python3 "$DEST/bin/python"
  if [[ -f "$DEST/pyvenv.cfg" ]]; then
    python3 - "$DEST/pyvenv.cfg" "$DEST/bin" <<'PYEOF'
import sys
from pathlib import Path

cfg = Path(sys.argv[1])
lines = []
for line in cfg.read_text(encoding="utf-8").splitlines():
    if line.strip().startswith("home"):
        lines.append(f"home = {sys.argv[2]}")
    else:
        lines.append(line)
cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
PYEOF
  fi
  echo "Self-contained interpreter: $DEST/bin/$(basename "$REAL_PY")"
fi

echo "Done. Rebuild with: cargo tauri build"
