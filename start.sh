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

# --- 依赖检查 (使用 uv run，与 run.py 保持一致) ---
check_python_deps() {
    if ! command -v uv >/dev/null 2>&1; then
        echo "错误：未找到 uv，请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi

    # 优先使用项目 .venv，其次用 uv sync 安装
    if [ ! -d "$PROJECT_DIR/.venv" ]; then
        echo "未找到 .venv，正在运行 uv sync..."
        uv sync --directory "$PROJECT_DIR"
    fi

    uv run --directory "$PROJECT_DIR" python -c "
deps = [
    ('langchain_openai', 'langchain-openai'),
    ('langchain_core', 'langchain-core'),
    ('requests', 'requests'),
    ('bs4', 'beautifulsoup4'),
    ('readability', 'readability-lxml'),
    ('docx', 'python-docx'),
    ('fitz', 'PyMuPDF'),
    ('mammoth', 'mammoth'),
    ('validators', 'validators'),
    ('pydantic', 'pydantic'),
    ('tiktoken', 'tiktoken'),
    ('markdownify', 'markdownify'),
    ('yaml', 'PyYAML'),
    ('markdown', 'markdown'),
    ('jieba', 'jieba'),
    ('PIL', 'pillow'),
    ('html2text', 'html2text'),
    ('watchdog', 'watchdog'),
    ('send2trash', 'send2trash'),
]
import sys
missing = []
for mod, pkg in deps:
    try:
        __import__(mod)
    except ImportError:
        missing.append(pkg)
if missing:
    print('缺少 Python 依赖: ' + ' '.join(missing))
    print('请运行: uv sync')
    sys.exit(1)
print('Python 依赖检查通过')
" || { echo "Python 依赖不全，请先运行: uv sync"; exit 1; }
}

check_python_deps

if [ "$TAURI_DEV" = true ]; then
    echo "模式: 开发模式 (dev)"
    cargo tauri dev 2>&1
else
    echo "模式: 发布构建 (build)"
    cargo tauri build 2>&1
fi
