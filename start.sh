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

    # 优先使用项目 .venv；创建或补齐依赖时默认带上 RAG（除非用户在设置里删除了 RAG 组件）
    if [ ! -d "$PROJECT_DIR/.venv" ]; then
        echo "未找到 .venv，正在运行 uv sync（含 dev + rag）..."
        uv run --directory "$PROJECT_DIR" python -c "
from pathlib import Path
from utils.deps_sync import run_uv_sync
ok, msg = run_uv_sync(project_dir=Path('$PROJECT_DIR'))
if not ok:
    print(msg)
    raise SystemExit(1)
" || { echo "uv sync 失败，请手动运行: cd \"$PROJECT_DIR\" && uv sync --extra dev --extra rag"; exit 1; }
    fi

    # 若 RAG 未主动删除但包缺失，自动 sync 补齐
    uv run --directory "$PROJECT_DIR" python -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')
from run import check_dependencies, _rag_deps_required
if _rag_deps_required():
    import importlib
    missing = []
    for pkg, mod in [('bm25s','bm25s'),('fastembed','fastembed'),('zvec','zvec'),('FlagEmbedding','FlagEmbedding')]:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        from pathlib import Path
        from utils.deps_sync import run_uv_sync
        print('检测到 RAG 依赖缺失，正在 uv sync 补齐…')
        ok, msg = run_uv_sync(project_dir=Path('$PROJECT_DIR'))
        if not ok:
            print(msg)
            sys.exit(1)
" || { echo "RAG 依赖补齐失败"; exit 1; }

    # 复用 run.py 的依赖检查逻辑（读取 pyproject.toml 全部依赖），避免维护两份列表
    uv run --directory "$PROJECT_DIR" python -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')
from run import check_dependencies
if not check_dependencies():
    sys.exit(1)
print('Python 依赖检查通过')
" || { echo "Python 依赖不全，请先运行: uv sync --extra dev --extra rag"; exit 1; }
}

check_python_deps

if [ "$TAURI_DEV" = true ]; then
    echo "模式: 开发模式 (dev)"
    cargo tauri dev 2>&1
else
    echo "模式: 发布构建 (build)"
    cargo tauri build 2>&1
fi
