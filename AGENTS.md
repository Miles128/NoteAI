# AGENTS.md

本文件为 AI 编码助手（Claude Code、Codex、Jcode、Trae Agent 等）提供 NoteAI 仓库的工作指南。它合并了原 `AGENTS.md` 与 `.trae/rules/project_rules.md`，以当前代码实际为准。

---

## 1. 项目规则

### 1.1 模块化要求

- **项目必须模块化**：每个功能模块独立成文件/目录，职责单一，禁止在单文件中混合多个不相关功能。
- **前端模块化**：JS/CSS 按功能拆分文件，通过统一入口加载，禁止所有代码堆在一个文件中。
- **后端模块化**：Python 按功能拆分模块（如 `note_integration.py`、`web_download.py`），通过 `__init__.py` 统一导出。
- **模块间通信**：通过明确的接口/函数调用交互，禁止模块间直接操作彼此内部状态。

### 1.2 技术架构

- **前端**：Tauri v2 + 原生 HTML/CSS/JS。
- **后端**：Python sidecar，通过 stdin/stdout JSON-RPC 与前端通信。
- **前端调用后端**：统一使用 `window.api` 对象（定义在 `webui/js/api.js`），禁止使用其他兼容层。
- **界面风格**：整体对标 Obsidian 应用。

### 1.3 Prompt 管理

所有传递给大模型的系统提示词必须放在 `prompts/` 目录下，禁止在业务代码中直接内联定义系统提示词。

- `prompts/yaml/*.yaml` 是**单一事实来源**；`prompts/__init__.py` 通过 `prompts/loader.py` 在导入时解析为常量。
- 提示词中可包含占位变量（如 `{topic_name}`、`{content}`），业务代码使用 `.format()` 填充。
- 新增提示词：先在 `prompts/yaml/` 添加 YAML，再在 `prompts/__init__.py` 导出对应常量。

### 1.4 应用启动

启动应用必须通过 Tauri 入口，禁止直接用浏览器打开 `webui/index.html` 或用 `python -m http.server` 等方式启动：

```bash
uv run python run.py   # 开发者启动器：检查依赖后执行 cargo tauri dev
```

不要与 `python/main.py`（sidecar 进程入口，由 Tauri 壳拉起）混淆。

### 1.5 依赖管理

使用 `uv` 管理 Python 依赖，禁止直接使用系统 `pip install`：

```bash
uv sync --extra dev --extra rag   # 安装依赖（RAG 默认包含）
uv run pytest                     # 运行测试
```

依赖声明于 `pyproject.toml`；`uv.lock` 提交入库。前端依赖走 npm（`package.json`），`mcp-server/` 为独立 npm 包。

### 1.6 Git 仓库配置

- **远程仓库名**：`NoteAI`（不是 `origin`），SSH 地址 `git@github.com:Miles128/NoteAI.git`，禁止 HTTPS 推送。
- **推送**：`git push NoteAI <branch-name>`。
- **PR 流程**：推送后使用 `gh pr create --base main` 创建 PR，再 `gh pr checks` 确认 CI，形成"推送 → 建 PR → 确认 CI"闭环。

---

## 2. 构建与测试

```bash
uv sync --extra dev --extra rag   # 安装依赖
uv run pytest                     # 运行全部测试（~69 单元 + 3 集成测试模块）
uv run python run.py              # 启动 Tauri dev 模式（检查依赖 + cargo tauri dev）
```

不要直接使用 `python run.py`，除非系统 Python 已安装项目依赖；开发一律用 `uv run python run.py`。

测试位于 `tests/`，通过 `pyproject.toml` 配置（`pythonpath = [".", "python"]`）。使用 `@pytest.fixture` 进行测试设置（如 `test_rpc_router.py`）。

## 3. 架构

```
Tauri v2 shell (src-tauri/)
  ├── webui/ (静态 HTML/CSS/JS，由 Tauri 加载)
  └── Python sidecar: stdin/stdout JSON-RPC (python/sidecar/)
```

**通信流程**：前端 JS → `window.api`（Tauri invoke）→ Rust → 拉起 Python sidecar → stdin/stdout JSON-RPC → `server.py:main()` 逐行读取，通过 `RpcRouter` 分发。

**Python sidecar**（`python/sidecar/server.py`）：`SidecarServer` 实例化 17 个 handler（cli_agent、component、config、files、ingest、intel、job、kb、links、mcp_config、rag、reliability、semantic、tags、topics、transfer、workspace），每个都是 `BaseHandler` 的子类。`BaseHandler` 通过显式 `@property` 访问器代理 server 属性（如 `config`、`_send_response`、`_resolve_path`、`_link_discovery_lock`）——handler 需要访问新的 server 属性时，在 `base.py` 中添加 property。每个 handler 通过 `RpcRouter` 注册路由。

**请求分流**（`python/sidecar/intent_router.py`）：RAG 对话先经意图路由分类（问答/整理/闲聊等），再分发给对应链路；CLI Agent 桥接（`cli_agent_runner.py` + `cli_agent/`）将文件操作指令转交外部 CLI Agent 执行。

**RAG 流程**（`python/sidecar/rag/`）：query → HyDE rewrite → zvec 混合检索（dense 0.7 + BM25 0.3，bm25s；`ensure_bm25_index` 自动重建缺失的 BM25 索引）→ MMR 去重 → FlagReranker（bge-reranker-v2-m3）→ LLM 流式输出。Embedding 使用 `BAAI/bge-small-zh-v1.5`（512 维，fastembed）。注意：`embedder.py` 中的 `lexical_weights`（jieba TF-IDF）当前不参与检索，sparse 检索直接用 bm25s 对原始 query 文本。

**三层知识架构**：`Notes/`（原始 Markdown，不可变来源）→ `wiki/`（AI 编译的结构化知识）→ `Raw/`（原始 PDF/DOCX 归档）。配置项 `ABSTRACT_FOLDER = "wiki"`。

## 4. 关键约定

- **Config**：单例 `config` 在 `config/app_config.py` 导入时加载。不要直接实例化 `AppConfig`，使用 `from config import config` 或 `from config.settings import config`。工作区路径通过 `config/workspace_state.py` 持久化；运行时值是 `config.workspace_path`。
- **Frontmatter**：规范解析器是 `utils/text_utils.parse_frontmatter(text)` → `(meta_dict, body_str)`。handler 中应使用 `self._parse_frontmatter()` 或直接导入，避免手写正则。
- **LLM 调用**：统一走 `utils/llm_utils`。`_LLM_SEMAPHORE = Semaphore(4)` 限制并发；`call_llm_raw()` 使用 `_retry_with_backoff()` 对限流指数退避。同步与流式变体都遵守信号量。输入 prompt 通过 `_clamp_prompt_text()` 截断到 `config.max_context_tokens`。
- **Chunk ID**：`hashlib.sha256(f"{file_path}::{section_title or ''}::{content[:100]}".encode()).hexdigest()[:16]`，位于 `chunker.py:155`。注意 `section_title` 可能为 `None`。
- **线程安全**：`SidecarServer` 使用锁保护 stdout（`_stdout_lock`）、缓存（`_cache_lock`）、运行中任务、watcher 防抖、link discovery。RAG 对话通过 `_rag_chat_lock` 单线程化。
- **文件监听**：watchdog 监听工作区；3 秒防抖；忽略点文件、`wiki/` 目录及非媒体后缀。
- **工作区路径**：始终使用 `config.workspace_path`，禁止硬编码。`scripts/` 中的脚本如需导入项目模块，先执行 `sys.path.insert(0, str(Path(__file__).parent.parent))`，再从 `config.settings` 导入。

## 5. 关键陷阱

- **`rag/index.py:delete_by_file()`**：先查询 chunks 再删除（此前是 delete-then-query；zvec 的最终一致性可能丢失 sparse 索引条目）。
- **`rag/retriever.py:_rerank()`**：不再用 `rerank_score` 覆盖 `score`，两者同时保留；rerank 后排序使用 `rerank_score`。
- **`rag_chat_with_actions` RPC 已移除**：它只是 `rag_chat` 的别名。文件操作现在通过 CLI Agent 对话框完成（PRD §3.8）。内置的 `agent_runner.py` / `agent_handler.py`（6 个结构化工具）已删除。
- **`rag/index.py:hybrid_search()`**：sparse-only 命中会查询 zvec 的 body text；空 chunk 被丢弃（`filter_usable_chunks`），过期的 sparse id 被清理。
- **Embedder 模块**（`rag/embedder.py`）：HF 环境变量（`HF_ENDPOINT`、`NO_PROXY`）与 `FASTEMBED_CACHE_PATH` 在首次加载模型时惰性设置，而非导入时。使用 hf-mirror.com。
- **主题分配**：逻辑分布在 `utils/topic_assigner.py`、`topic_classifier.py`、`topic_file_ops.py`、`topic_manager.py`、`topic_dedup.py`、`topic_pending.py`、`topic_merge.py`。新增主题相关逻辑放在这一组模块中，不要继续膨胀 handler。
- **`IGNORED_DIRS`**（`constants.py`）：小写匹配集合 `{"ai", "noteai", ".noteai", ".NoteAI", "wiki", "ai wiki", "ai-wiki", "ai_wiki", "aiwiki"}`。
- **WIKI.md 操作**：生产写入通过 `sidecar/wiki_utils.py`；底层解析/CRUD 辅助函数在 `utils/wiki_manager.py`、`utils/wiki_crud.py`、`utils/wiki_sync.py`。
- **凭据存储**：环境变量为只读覆盖；持久化的 API key、云密码与 token 使用 Fernet 加密文件存放于 `SYSTEM_APP_DATA_DIR/credentials/`。不要使用 macOS Keychain 或其他系统钥匙串。PBKDF2 派生密钥与每安装随机 secret 只提供混淆，非硬件级保护。
- **命题验证**（`python/sidecar/semantic/claim_verifier.py`）：基于同主题活跃证据交叉验证命题，结果写入 `claim_verifications` 表，语义工作台展示验证结论；抽取提示词见 `prompts/yaml/claim_verify.yaml`。
- **笔记合并建议**（`utils/note_merge_analyzer.py`，RPC `get_note_merge_suggestions`）：利用 RAG 索引（zvec 向量相似度）与语义库（实体/概念共享计数）分析笔记合并候选，分级 A（≥0.96 同源）/B（≥0.92 深度重叠）/C（≥0.85 主题关联）。只读分析；索引被占用或未建立时优雅降级；stale 过滤（索引中已删除/移动的文件剔除）。执行合并走 `merge_suggested_notes` RPC，复用 `sidecar/duplicate_review.py` 的 `merge_note_group`（LLM 整合 + send2trash 删除 + .links.json 链接重定向）。注意：`chunk_similarity.py` 是另一条既有向量相似度路径（`scan_merge_candidates`，chunk 级图），与文档级建议互补不重复。
- **RAG 端点**除 LLM 信号量外无额外速率限制。

## 6. 项目记忆

- **`webui/js/`**：vanilla JS IIFE 模块挂载在 `window.*`，无 bundler，无虚拟 DOM。状态在 `window.AppState` 与 `window.state`。`main.mjs` 是唯一的 ES module。
- **右侧检查器**（`webui/js/inspector.js`）：AI/CLI/属性/反向链接/语义 多 Tab 面板；笔记的语义参数（实体/概念/命题与证据/相关）在「语义」Tab 中展示，点击实体/概念经 `SemanticWorkbenchModule.openObject` 打开工作台详情。
- **Tauri sidecar**：配置在 `src-tauri/tauri.conf.json`。Python 二进制通过 `python/main.py` → `sidecar.server.main()` 解析。
- **测试覆盖**：~69 个单元测试模块 + 3 个集成测试模块（含 `tests/integration/test_sidecar_contracts.py`）；发布前运行 `uv run pytest`。
- **Prompts**：`prompts/yaml/*.yaml` 是单一事实来源；`prompts/__init__.py` 经 `prompts/loader.py` 在导入时解析常量。
- **Sidecar Python**：开发使用项目 `.venv`；发布可通过 `scripts/bundle_sidecar_python.sh` 打包到 `src-tauri/resources/sidecar-python`，或设置 `NOTEAI_PYTHON`。
- **`rag_enabled`**：默认 `True`（`config/app_config.py`）；关闭时使用 `sidecar/classic_retriever.py` 传统检索。

---

## 7. 产品行为规范

- **链接索引**（`utils/link_indexer.py`，存储于 `workspace/.links.json`）：保存触发的 `discover_cross_refs_for_file(use_llm=False)` 只产生「正文提及标题 / 对方摘要提及标题 / 共享实体概念」三类真实引用，一律 `pending` 待人工确认；**禁止**再引入「共享标签 / 语义相关 / 邻居传播 / 同主题」等对称弱启发式（曾导致 92% 链接双向爆炸）。全库双向补链走 `backfill_semantic_bidirectional`（实体/概念共享 ≥ `_BIDIRECTIONAL_SHARE_MIN=6`）；历史弱链接清洗走 `purge_weak_links`。两个 RPC 均已在 Rust 白名单（`src-tauri/src/rpc.rs`），api.js 未暴露属预期。
- **综述写作规则**（硬化于 `prompts/yaml/topic_survey.yaml` 与 `prompts/yaml/cascade.yaml` 的 `CASCADE_SURVEY_NEW_PROMPT`/`CASCADE_SURVEY_UPDATE_PROMPT`）：综述定位为**简略概括而非复述**——每个知识点用 1-3 句讲清核心结论；完整代码、长表格、逐步操作等深度内容一律不写入综述，用「详见：文件名.md」替代；篇幅约为原始笔记总量的 20%-40%。修改综述提示词或撰写综述时须遵守此原则。
- NoteAI 内置 AI 功能（自动分类、标签提取、知识问答、综述生成、主题存储格式、两层记忆体系等）的产品行为规范见 [documents/PRD.md](documents/PRD.md) 第 12 章「通用 AI 行为规范」。编码代理修改仓库时无需加载该章节；仅当改动涉及这些产品行为时才查阅。
