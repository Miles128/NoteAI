# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, Jcode, etc.) when working with this repository.

> # Build & Test

```bash
uv sync                    # install deps
uv sync --extra dev        # include test deps
pytest                     # run all tests (40+ test modules)
python run.py              # start Tauri dev mode (checks deps + cargo tauri dev)
```

Tests live in `tests/`, configured via `pyproject.toml` (`pythonpath = [".", "python"]`). Uses `@pytest.fixture` for test setup (e.g. `test_rpc_router.py`).

## Architecture

```
Tauri v2 shell (src-tauri/)
  ├── webui/ (static HTML/CSS/JS, loaded by Tauri)
  └── Python sidecar: stdin/stdout JSON-RPC (python/sidecar/)
```

**Communication flow**: Frontend JS → `window.api` (Tauri invoke) → Rust → spawns Python sidecar → JSON-RPC over stdin/stdout → `server.py:main()` reads lines, dispatches via `RpcRouter`.

**Python sidecar** (`python/sidecar/server.py`): `SidecarServer` instantiates 14 handlers, each a subclass of `BaseHandler`. `BaseHandler` uses explicit `@property` accessors to proxy server attributes (e.g. `config`, `_send_response`, `_resolve_path`, `_link_discovery_lock`) — add new properties in `base.py` when handlers need access to new server attributes. Each handler registers routes with `RpcRouter`.

**RAG pipeline** (`python/sidecar/rag/`): query → HyDE rewrite → zvec hybrid search (dense 0.7 + BM25 0.3 via bm25s; `ensure_bm25_index` auto-rebuilds missing BM25) → MMR dedup → FlagReranker (bge-reranker-v2-m3) → LLM stream. Embeddings: BAAI/bge-small-zh-v1.5 (512d) via fastembed. `lexical_weights` in embedder is jieba TF-IDF (query fallback text only).

**Three-layer knowledge architecture**: `Notes/` (raw markdown, immutable source) → `wiki/` (AI-compiled structured knowledge) → `Raw/` (original PDF/DOCX archives). Config: `ABSTRACT_FOLDER = "wiki"`.

## Key conventions

- **Config**: singleton `config` loaded at import time from `config/app_config.py`. Never instantiate `AppConfig` directly — import `from config import config` or `from config.settings import config`. Persist workspace path through `config/workspace_state.py`; `config.workspace_path` is the runtime value.
- **Frontmatter**: canonical parser is `utils/text_utils.parse_frontmatter(text)` → `(meta_dict, body_str)` (re-exported from `sidecar.textutils` for backward compatibility). All handlers should use `self._parse_frontmatter()` or direct import — avoid manual regex.
- **LLM calls**: go through `utils/llm_utils`. `_LLM_SEMAPHORE = Semaphore(4)` limits concurrency. `call_llm_raw()` uses `_retry_with_backoff()` with exponential backoff for rate limits. Both sync and stream variants now respect the semaphore. Input prompts are clamped to `config.max_context_tokens` via `_clamp_prompt_text()`.
- **Chunk IDs**: generated via `hashlib.sha256(f"{file_path}::{section_title or ''}::{content[:100]}".encode()).hexdigest()[:16]` in `chunker.py:155`. Note: `section_title` can be `None`.
- **Thread safety**: `SidecarServer` uses locks for stdout (`_stdout_lock`), cache (`_cache_lock`), running tasks, watcher debounce, and link discovery. RAG chat is single-threaded via `_rag_chat_lock`.
- **File watching**: watchdog monitors workspace; 3s debounce; ignores dotfiles, `wiki/` directory, and non-media suffixes.
- **Workspace paths**: always use `config.workspace_path` — never hardcode. Scripts in `scripts/` should import from `config.settings` (add `sys.path.insert(0, str(Path(__file__).parent.parent))` first).

## Critical gotchas

- **`rag/index.py:delete_by_file()`**: queries chunks BEFORE deleting (was delete-then-query; zvec eventual consistency could lose track of sparse index entries).
- **`rag/retriever.py:_rerank()`**: no longer overwrites `score` with `rerank_score` — both fields preserved. Sort post-rerank uses `rerank_score`.
- **`rag_chat_with_actions`** RPC removed: was an alias for `rag_chat`. File operations now go through the CLI agent dialog (§3.8 of PRD). The built-in `agent_runner.py` / `agent_handler.py` (6 structured tools) have been deleted.
- **`rag/index.py:hybrid_search()`**: sparse-only hits query zvec for body text; empty chunks are dropped (`filter_usable_chunks`) and stale sparse ids purged.
- **Embedder module** (`rag/embedder.py`): HF environment variables (`HF_ENDPOINT`, `NO_PROXY`) and `FASTEMBED_CACHE_PATH` are set lazily via `_ensure_hf_env()` / `_ensure_fastembed_cache()` on first model load, not at import time. Uses hf-mirror.com.
- **Topic assignment** has been split across `utils/topic_assigner.py`, `topic_classifier.py`, `topic_file_ops.py`, `topic_pending.py`, and `topic_wiki_manager.py`; keep new topic logic in that cluster instead of growing handlers.
- **`IGNORED_DIRS`** (constants.py): lowercased match on `{"ai", "noteai", ".noteai", ".NoteAI", "wiki", "ai wiki", "ai-wiki", "ai_wiki", "aiwiki"}`.
- **WIKI.md operations**: production writes should enter through `sidecar/wiki_utils.py`; lower-level parsers/CRUD helpers remain under `utils/wiki_manager.py` and `utils/topic_wiki_manager.py`.
- **API key storage**: 3-tier priority: env var > OS keyring > Fernet-encrypted file (`api_key.dat`) in `~/Library/Application Support/NoteAI/`. Fallback file uses PBKDF2-derived key with per-installation random salt — this is obfuscation, not strong encryption.
- **No rate limiting** on RAG endpoints beyond the LLM semaphore.

## Project memory

- **`webui/js/`**: vanilla JS IIFE modules on `window.*`, no bundler, no virtual DOM. State in `window.AppState` and `window.state`. `main.mjs` is the only ES module.
- **Tauri sidecar**: configured in `src-tauri/tauri.conf.json`. Python binary resolved via `python/main.py` → `sidecar.server.main()`.
- **Test coverage**: \~30+ unit test modules + `tests/integration/test_sidecar_contracts.py`; run `uv run pytest` before release.
- **Prompts**: Python constants in `prompts/` with parallel `prompts/yaml/` (loader supports both).
- **Sidecar Python**: dev uses project `.venv`; release can bundle `src-tauri/resources/sidecar-python` via `scripts/bundle_sidecar_python.sh`, or set `NOTEAI_PYTHON`.
- **`rag_enabled`**: default `True` in `config/app_config.py`; classic retrieval via `sidecar/classic_retriever.py` when off.

***

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
- 分隔符: `>`
- 最多三层，三级下不再设子题

## 两层记忆体系

NoteAI 有两层 Memory，均与工作区绑定（切换工作区即切换画像与对话记忆）：

### L1：用户画像（工作区级）

位置：`<工作区>/.ai_memory/user_profile.json`（含 `profile_md` 字段）

- 用户身份、偏好、知识背景
- 由设置界面的「用户画像」功能维护
- RAG 对话可读取并用于查询改写

### L2：工作区 Memory（RAG 会话）

位置：`<工作区>/.noteai/memory/`

- 该工作区的 RAG 对话记忆
- 工作区特定的 AI 运行时数据

### 工作区运行时目录

```
<工作区>/
├── .noteai/
│   ├── memory/       # RAG 会话记忆（L2）
│   ├── rag_index/    # zvec + bm25s 向量索引
│   └── ingest_state.json 等
├── .ai_memory/
│   ├── user_profile.json   # 用户画像（L1）
│   └── project_rules.md    # 项目规则
└── wiki/
    └── log.md        # 统一变更日志（入库/级联/Lint/归档）
```

> 旧文档中的 `NoteAI/`、`NoteAI/profile.md` 为别名，请以 `.noteai`、`.ai_memory` 为准。

