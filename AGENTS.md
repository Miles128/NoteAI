# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Build & Test

```bash
uv sync                    # install deps
uv sync --extra dev        # include test deps
pytest                     # run all tests (11 test files)
python run.py              # start Tauri dev mode (checks deps + cargo tauri dev)
```

Tests live in `tests/`, configured via `pyproject.toml` (`pythonpath = [".", "python"]`). No conftest, no fixtures.

## Architecture

```
Tauri v2 shell (src-tauri/)
  ├── webui/ (static HTML/CSS/JS, loaded by Tauri)
  └── Python sidecar: stdin/stdout JSON-RPC (python/sidecar/)
```

**Communication flow**: Frontend JS → `window.api` (Tauri invoke) → Rust → spawns Python sidecar → JSON-RPC over stdin/stdout → `server.py:main()` reads lines, dispatches via `RpcRouter`.

**Python sidecar** (`python/sidecar/server.py`): `SidecarServer` instantiates 12 handlers, each a subclass of `BaseHandler`. `BaseHandler.__getattr__` proxies to server via `_PROXY_ALLOWED` whitelist — handlers can access server attributes without explicit injection. Each handler registers routes with `RpcRouter`.

**RAG pipeline** (`python/sidecar/rag/`): query → HyDE rewrite → Milvus Lite hybrid search (dense 0.7 + sparse 0.3) → MMR dedup → FlagReranker (bge-reranker-v2-m3) → LLM stream. Embeddings: BAAI/bge-small-zh-v1.5 (512d) via fastembed. Sparse: jieba TF-IDF.

**Three-layer knowledge architecture**: `Notes/` (raw markdown, immutable source) → `wiki/` (AI-compiled structured knowledge) → `Raw/` (original PDF/DOCX archives). Config: `ABSTRACT_FOLDER = "wiki"`.

## Key conventions

- **Config**: singleton `config` loaded at import time from `config/app_config.py:318`. Never instantiate `AppConfig` directly — import `from config import config` or `from config.settings import config`.
- **Frontmatter**: canonical parser is `sidecar.textutils.parse_frontmatter(text)` → `(meta_dict, body_str)`. Many handlers still use manual regex `r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---'` — prefer `parse_frontmatter` for new code.
- **LLM calls**: go through `utils/llm_utils`. `_LLM_SEMAPHORE = Semaphore(4)` limits concurrency. `call_llm_raw()` uses `_retry_with_backoff()` with exponential backoff for rate limits. Both sync and stream variants now respect the semaphore.
- **Chunk IDs**: generated via `hashlib.md5(f"{file_path}::{section_title}::{content[:100]}".encode()).hexdigest()[:12]` in `chunker.py:169`. Note: `section_title` can be `None`.
- **Thread safety**: `SidecarServer` uses locks for stdout (`_stdout_lock`), cache (`_cache_lock`), running tasks, watcher debounce, and link discovery. RAG chat is single-threaded via `_rag_chat_lock`.
- **File watching**: watchdog monitors workspace; 3s debounce; ignores dotfiles, `wiki/` directory, and non-media suffixes.
- **Workspace paths**: always use `config.workspace_path` — never hardcode. Scripts in `scripts/` should import from `config.settings` (add `sys.path.insert(0, str(Path(__file__).parent.parent))` first).

## Critical gotchas

- **`modules/abstract_generator.py`**: f-strings now use real `\n` (were literal `\\n` before fix — verify if regenerating surveys).
- **`rag/index.py:delete_by_file()`**: queries chunks BEFORE deleting (was delete-then-query; Milvus eventual consistency could lose track of sparse index entries).
- **`rag/retriever.py:_rerank()`**: no longer overwrites `score` with `rerank_score` — both fields preserved. Sort post-rerank uses `rerank_score`.
- **`rag_handler.py:_execute_single_action()`** (line 374): lets LLM generate and execute arbitrary code. This is a security risk — any prompt injection can escape.
- **`rag/index.py:hybrid_search()`** lines 212-224: sparse-only results get empty `content`/`file_path` — these reach the LLM with no usable text.
- **Embedder module import** (`rag/embedder.py:7-11`): sets `os.environ["HF_ENDPOINT"]` and `NO_PROXY` at import time — affects entire process. Uses hf-mirror.com.
- **`topic_assigner.py`** is 2100+ lines — mixes AI classification, wiki management, file operations, and dedup. Split pending.
- **`IGNORED_DIRS`** (constants.py): lowercased match on `{"ai", "wiki", "ai wiki", "ai-wiki", "ai_wiki", "aiwiki"}`.
- **WIKI.md operations**: at least 5 different files manipulate WIKI.md with slightly different text parsing — easy to break consistency.
- **API key storage**: 3-tier priority: env var > OS keyring > base64-obfuscated file (`api_config.json`) in `~/Library/Application Support/NoteAI/`. Base64 is NOT encryption.
- **No rate limiting** on RAG endpoints beyond the LLM semaphore.

## Project memory

- **`webui/js/`**: vanilla JS IIFE modules on `window.*`, no bundler, no virtual DOM. State in `window.AppState` and `window.state`. `main.mjs` is the only ES module.
- **Tauri sidecar**: configured in `src-tauri/tauri.conf.json`. Python binary resolved via `python/main.py` → `sidecar.server.main()`.
- **Test coverage**: ~3-5% overall. No tests for any handler, RAG component, or business module. `tests/integration/test_sidecar_contracts.py` is the only integration test.
- **Prompts** live in `prompts/` as Python module constants. YAML migration in `prompts/yaml/` is stalled at ~4%.


---

# NoteAI 通用 AI 行为规范

以下规则适用于 NoteAI 内置 AI 功能（自动分类、标签提取、知识问答、综述生成等），作用于所有工作区。

## 标签规则

- 标签从文章内容自动提取（jieba 分词 + 词频）
- 标签应具备实际分类意义，避免过于泛化的词
- 优先使用中文标签
- 每篇文章建议 2-5 个标签

## 知识架构（三层）

```
Notes/        ← 原始笔记（Markdown，不可变来源）
wiki/         ← AI 编译的结构化知识（综述、WIKI.md 索引）
Raw/          ← 原始文件归档（PDF、DOCX、PPTX、图片等）
```

- **Notes**: 采集的文章。按主题分文件夹。文件标题 = 文件名 stem。
- **wiki**: AI 生成的产物。WIKI.md 仅含主题标题 + 文件列表。综述按主题存放。
- **Raw**: 非 Markdown 格式文件的归档区。

## AI 功能行为准则

1. **自动分类**: 以当前工作区 `wiki/GUIDE.md` 中定义的主题归类规则为准。不确定则标记 pending。
2. **标签提取**: 从标题和正文提取有区分度的关键词，避免通用词。
3. **综述生成**: 针对二级主题，综合该主题下所有笔记内容。
4. **知识问答**: 优先从知识库检索，结合工作区的主题体系给出回答。
5. **级联更新**: 新资料入库时，主动检查并更新受影响的已有综述和 WIKI 条目。

## 文件命名规范

- 文件名 = 文章标题
- 中文命名优先
- 避免特殊字符（`/ \ : * ? " < > |`）
- 综述文件: `{主题名}_综述.md`

## 主题存储格式（所有工作区通用）

- YAML frontmatter: `topic: 一级 > 二级 > 三级`
- 文件系统: `Notes/一级/二级/三级/文件名.md`
- 分隔符: ` > `
- 最多三层，三级下不再设子题

## 两层记忆体系

NoteAI 有两层 Memory，分别存储在不同位置：

### L1：长期用户画像（跨工作区）

位置：`NoteAI项目根目录/NoteAI/profile.md`

- 用户身份、偏好、知识背景
- 所有工作区共享
- 由设置界面的"用户画像"功能维护

### L2：工作区 Memory（工作区专属）

位置：`<工作区>/NoteAI/memory/`

- 该工作区的 RAG 对话记忆
- 工作区特定的 AI 运行时数据
- 与笔记内容相关但不修改笔记本身

### 工作区 NoteAI 目录完整结构

```
<工作区>/NoteAI/
├── GUIDE.md          # 工作区主题归类规则
├── memory/           # 工作区 Memory
├── logs/             # NoteAI 操作日志
└── rag_index/        # RAG 向量索引数据
```
