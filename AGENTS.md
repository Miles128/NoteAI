# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, Jcode, etc.) when working with this repository.

> # Build & Test

```bash
uv sync --extra dev --extra rag   # install deps (RAG included by default; see Settings → Components to remove)
uv sync --extra dev               # after removing RAG in Settings only
uv run pytest              # run all tests (~69 unit + 3 integration test modules)
uv run python run.py       # start Tauri dev mode with the project virtualenv
```

Do not use `python run.py` directly unless the system Python has the project dependencies installed; use `uv run python run.py` for development.

Tests live in `tests/`, configured via `pyproject.toml` (`pythonpath = [".", "python"]`). Uses `@pytest.fixture` for test setup (e.g. `test_rpc_router.py`).

## Architecture

```
Tauri v2 shell (src-tauri/)
  ├── webui/ (static HTML/CSS/JS, loaded by Tauri)
  └── Python sidecar: stdin/stdout JSON-RPC (python/sidecar/)
```

**Communication flow**: Frontend JS → `window.api` (Tauri invoke) → Rust → spawns Python sidecar → JSON-RPC over stdin/stdout → `server.py:main()` reads lines, dispatches via `RpcRouter`.

**Python sidecar** (`python/sidecar/server.py`): `SidecarServer` instantiates 16 handlers, each a subclass of `BaseHandler`. `BaseHandler` uses explicit `@property` accessors to proxy server attributes (e.g. `config`, `_send_response`, `_resolve_path`, `_link_discovery_lock`) — add new properties in `base.py` when handlers need access to new server attributes. Each handler registers routes with `RpcRouter`.

**RAG pipeline** (`python/sidecar/rag/`): query → HyDE rewrite → zvec hybrid search (dense 0.7 + BM25 0.3 via bm25s; `ensure_bm25_index` auto-rebuilds missing BM25) → MMR dedup → FlagReranker (bge-reranker-v2-m3) → LLM stream. Embeddings: BAAI/bge-small-zh-v1.5 (512d) via fastembed. Note: `lexical_weights` in `embedder.py` is computed from jieba TF-IDF but is currently unused for retrieval; sparse search uses bm25s on raw query text.

**Three-layer knowledge architecture**: `Notes/` (raw markdown, immutable source) → `wiki/` (AI-compiled structured knowledge) → `Raw/` (original PDF/DOCX archives). Config: `ABSTRACT_FOLDER = "wiki"`.

## Key conventions

- **Config**: singleton `config` loaded at import time from `config/app_config.py`. Never instantiate `AppConfig` directly — import `from config import config` or `from config.settings import config`. Persist workspace path through `config/workspace_state.py`; `config.workspace_path` is the runtime value.
- **Frontmatter**: canonical parser is `utils/text_utils.parse_frontmatter(text)` → `(meta_dict, body_str)`. All handlers should use `self._parse_frontmatter()` or direct import — avoid manual regex.
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
- **Topic assignment** has been split across `utils/topic_assigner.py`, `topic_classifier.py`, `topic_file_ops.py`, and `topic_pending.py`; keep new topic logic in that cluster instead of growing handlers.
- **`IGNORED_DIRS`** (constants.py): lowercased match on `{"ai", "noteai", ".noteai", ".NoteAI", "wiki", "ai wiki", "ai-wiki", "ai_wiki", "aiwiki"}`.
- **WIKI.md operations**: production writes should enter through `sidecar/wiki_utils.py`; lower-level parsers/CRUD helpers remain under `utils/wiki_manager.py` and `utils/wiki_crud.py`.
- **Credential storage**: environment variables are read-only overrides; persistent API keys, cloud passwords, and tokens use Fernet-encrypted files under `SYSTEM_APP_DATA_DIR/credentials/`. Do not use macOS Keychain or another OS keyring. The PBKDF2-derived key and per-installation secret provide obfuscation, not hardware-backed protection.
- **No rate limiting** on RAG endpoints beyond the LLM semaphore.

## Project memory

- **`webui/js/`**: vanilla JS IIFE modules on `window.*`, no bundler, no virtual DOM. State in `window.AppState` and `window.state`. `main.mjs` is the only ES module.
- **Tauri sidecar**: configured in `src-tauri/tauri.conf.json`. Python binary resolved via `python/main.py` → `sidecar.server.main()`.
- **Test coverage**: \~69 unit test modules + 3 integration modules (incl. `tests/integration/test_sidecar_contracts.py`); run `uv run pytest` before release.
- **Prompts**: `prompts/yaml/*.yaml` is the single source of truth; `prompts/__init__.py` resolves constants via `prompts/loader.py` at import time.
- **Sidecar Python**: dev uses project `.venv`; release can bundle `src-tauri/resources/sidecar-python` via `scripts/bundle_sidecar_python.sh`, or set `NOTEAI_PYTHON`.
- **`rag_enabled`**: default `True` in `config/app_config.py`; classic retrieval via `sidecar/classic_retriever.py` when off.

***

> NoteAI 内置 AI 功能（自动分类、标签提取、知识问答、综述生成等）的产品行为规范已迁移至 [documents/PRD.md](documents/PRD.md) 第 12 章「通用 AI 行为规范」。编码代理修改仓库时无需加载该章节；仅当改动涉及这些产品行为时才查阅。
