# NoteAI

基于 **Tauri 2** 的 Markdown 知识库桌面应用：本地 **HTML/CSS/JS** 界面，**Python sidecar**（`python/sidecar/`，标准输入/输出 JSON）负责下载、转换、主题/标签/链接与 LLM 能力。

## 功能概览

- 网页文章批量下载并转 Markdown，可选 AI 辅助
- PDF / DOCX / PPTX / TXT 等转 Markdown
- 主题提取、WIKI 与标签、双链与关系图
- 侧栏文件树、编辑与预览、工作区热更新（需 **watchdog**）

## 环境要求

- **Python 3.10+**
- **Rust** 与 [Tauri CLI](https://v2.tauri.app/)（`cargo tauri` 或 `npx @tauri-apps/cli`）
- 推荐使用 [**uv**](https://docs.astral.sh/uv/) 管理依赖

## 安装依赖（单一来源）

运行时依赖**只**在 `pyproject.toml` 的 `[project] dependencies` 中维护；`uv.lock` 为锁定文件（使用 `uv` 时）。

```bash
cd NoteAI
uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv sync
uv sync --extra dev         # 含 pytest
```

使用 pip 时（从仓库根目录）：

```bash
pip install -e .
pip install -e ".[dev]"
```

`requirements.txt` 仅含可编辑安装说明，**不再**维护与 `pyproject.toml` 重复的平铺包列表。

## 运行

**开发（Tauri + sidecar）**（仓库根目录）：

```bash
python run.py
```

会调用 `cargo tauri dev` 并启动 Python `python/main.py` 作为子进程 sidecar。

`webui/app.py` 已删除；统一入口为 `python run.py`。

## 目录结构（摘要）

| 路径 | 说明 |
|------|------|
| `run.py` | 根启动器：检查依赖后执行 `cargo tauri dev` |
| `src-tauri/` | Tauri 壳、`py_call` 与 sidecar 启动 |
| `webui/` | 前端静态资源（`index.html`、JS/CSS） |
| `python/main.py` | sidecar 进程入口 |
| `python/sidecar/` | RPC 路由、`mixins` 业务拆分 |
| `config/`、`modules/`、`utils/`、`prompts/` | 配置与业务模块 |
| `docs/` | 说明与 API 文档 |

更多说明见 **[docs/README.md](docs/README.md)**。

## 测试

```bash
uv sync --extra dev
pytest
```

路径解析、主题树返回结构与预览路径契约见 `tests/integration/test_sidecar_contracts.py`。

## 许可证

MIT（见 `pyproject.toml`）
