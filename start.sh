#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "=== NoteAI 一键启动 ==="
echo ""

TAURI_DEV=true

for arg in "$@"; do
    case "$arg" in
        --release) TAURI_DEV=false ;;
        *) echo "未知参数: $arg"; exit 1 ;;
    esac
done

if [ "$TAURI_DEV" = true ]; then
    echo "模式: 开发模式 (dev)"
    cargo tauri dev 2>&1
else
    echo "模式: 发布构建 (build)"
    cargo tauri build 2>&1
fi
