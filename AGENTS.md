# AGENTS.md

本文件为 AI 编码助手（Claude Code、Codex、Jcode、Trae Agent 等）提供 NoteAI 仓库的工作指南。它合并了原 `AGENTS.md` 与 `.trae/rules/project_rules.md`，以当前代码开放现状为准。

---

## 1. 项目规则

### 1.1 模块化要求

- **项目必须模块化**：每个功能模块独立成文件/目录，职责单一，禁止在单文件中混合多个不相关功能。
- **前端模块化**：JS/CSS 按功能拆分文件，通过 `import` 或统一入口加载，禁止所有代码堆在一个文件中。
- **后端模块化**：Python 按功能拆分模块（如 `note_integration.py`、`web_download.py`），通过 `__init__.py` 统一导出，禁止在单文件中实现多个不相关功能。
- **模块间通信**：通过明确的接口/函数调用交互，禁止模块间直接操作彼此内部状态。

### 1.2 技术架构

- **前端**：Tauri v2 + HTML/CSS/JS。
- **后端**：Python sidecar，通过 stdin/stdout JSON-RPC 与前端通信。
- **前端调用后端**：统一使用 `window.api` 对象（定义在 `webui/js/api.js`），禁止使用 `pywebview` 或其他兼容层。
- **界面风格**：整体对标 Obsidian 应用。

### 1.3 Prompt 管理

所有传递给大模型的系统提示词必须单独保存到 `prompts/` 目录下的 Python 文件中，禁止在业务代码中直接内联定义系统提示词。

- 使用 Python 常量形式定义，如 `PROMPT_NAME = """..."""`。
- 提示词中可包含占位变量，如 `{topic_name}`、`{content}`。
- 业务代码使用 `from prompts.module import PROMPT_NAME` 导入，并用 `.format()` 填充变量。
- 常量名使用大写，单词间用下划线分隔，以 `_PROMPT` 结尾，例如 `TOPIC_EXTRACTION_PROMPT`。
- 文件名与功能模块对应，如 `note_integration.py`、`web_download.py`。
- `prompts/__init__.py` 必须使用 `from .module import PROMPT_NAME` 导出所有提示词。

### 1.4 应用启动

启动应用必须通过 Tauri：

```bash
# 正确
cargo tauri dev

# 错误
# 直接用浏览器打开 webui/index.html
# 使用 python -m http.server 等方式启动
```

### 1.5 Python 包安装

安装 Python 包必须使用 `uv pip install`，禁止使用 `pip install`。

```bash
uv pip install <package_name>
```

### 1.6 Git 仓库配置

- **远程仓库名称**：`NoteAI`（不是 `origin`）。
- **推送到远程**：`git push NoteAI <branch-name>`。
- **仓库地址**：`https://github.com/Miles128/NoteAI.git`。
- 创建 PR 时不使用 `gh cli`，通过 GitHub 网页完成。

---

## 2. 构建与测试

```bash
uv sync                    # 安装依赖
uv sync --extra dev        # 包含测试依赖
pytest                     # 运行所有测试（40+ 测试模块）
python run.py              # 启动 Tauri dev 模式（检查依赖 + cargo tauri dev）
```

测试位于 `tests/`，通过 `pyproject.toml` 配置（`pythonpath = [".", "python"]`）。使用 `@pytest.fixture` 进行测试设置。

---

## 3. 架构

```
Tauri v2 shell (src-tauri/)
  ├── webui/ (静态 HTML/CSS/JS，由 Tauri 加载)
  └── Python sidecar: stdin/stdout JSON-RPC (python/sidecar/)
```

**通信流程**：前端 JS → `window.api`（Tauri invoke）→ Rust → 启动 Python sidecar → stdin/stdout JSON-RPC → `server.py:main()` 逐行读取，通过 `RpcRouter` 分发。

**Python sidecar**（`python/sidecar/server.py`）：`SidecarServer` 实例化 14 个 handler，每个都是 `BaseHandler` 的子类。`BaseHandler` 通过显式 `@property` 访问器代理 server 属性（如 `config`、`_send_response`、`_resolve_path`、`_link_discovery_lock`）。当 handler 需要访问新的 server 属性时，在 `base.py` 中添加新的 property。每个 handler 通过 `RpcRouter` 注册路由。

**RAG 流程**（`python/sidecar/rag/`）：query → HyDE rewrite → zvec 混合检索（dense 0.7 + sparse 0.3）→ MMR 去重 → FlagReranker（bge-reranker-v2-m3）→ LLM 流式输出。Embedding 使用 `BAAI/bge-small-zh-v1.5`（512 维，fastembed）。Sparse 使用 jieba TF-IDF。

**三层知识架构**：`Notes/`（原始 Markdown，不可变来源）→ `wiki/`（AI 编译的结构化知识）→ `Raw/`（原始 PDF/DOCX 等归档）。配置项 `ABSTRACT_FOLDER = "wiki"`。

---

## 4. 关键约定

- **Config**：单例 `config` 在 `config/app_config.py` 导入时加载。不要直接实例化 `AppConfig`，使用 `from config import config` 或 `from config.settings import config`。工作区路径通过 `config/workspace_state.py` 持久化；运行时值是 `config.workspace_path`。
- **Frontmatter**：规范解析器是 `utils/text_utils.parse_frontmatter(text)` → `(meta_dict, body_str)`（从 `sidecar.textutils` 重新导出以兼容旧代码）。handler 中应使用 `self._parse_frontmatter()` 或直接导入，避免手写正则。
- **LLM 调用**：统一走 `utils/llm_utils`。`_LLM_SEMAPHORE = Semaphore(4)` 限制并发。`call_llm_raw()` 使用 `_retry_with_backoff()` 对限流进行指数退避。同步与流式变体都遵守信号量。输入 prompt 通过 `_clamp_prompt_text()` 截断到 `config.max_context_tokens`。
- **Chunk ID**：`hashlib.sha256(f"{file_path}::{section_title or ''}::{content[:100]}".encode()).hexdigest()[:16]`，位于 `chunker.py:155`。注意 `section_title` 可能为 `None`。
- **线程安全**：`SidecarServer` 使用锁保护 stdout（`_stdout_lock`）、缓存（`_cache_lock`）、运行中任务、watcher 防抖、link discovery。RAG 对话通过 `_rag_chat_lock` 单线程化。
- **文件监听**：watchdog 监听工作区；3 秒防抖；忽略点文件、`wiki/` 目录及非媒体后缀。
- **工作区路径**：始终使用 `config.workspace_path`，禁止硬编码。`scripts/` 中的脚本如需导入，先执行 `sys.path.insert(0, str(Path(__file__).parent.parent))`，再从 `config.settings` 导入。

---

## 5. 关键陷阱

- **`rag/index.py:delete_by_file()`**：先查询 chunks 再删除（以前是 delete-then-query；zvec 的最终一致性可能导致丢失 sparse 索引条目）。
- **`rag/retriever.py:_rerank()`**：不再用 `rerank_score` 覆盖 `score`，两者同时保留。rerank 后的排序使用 `rerank_score`。
- **`rag_chat_with_actions`** RPC 已移除：它只是 `rag_chat` 的别名。文件操作现在通过 CLI agent 对话框完成（PRD §3.8）。内置的 `agent_runner.py` / `agent_handler.py`（6 个结构化工具）已删除。
- **`rag/index.py:hybrid_search()`**：sparse-only 命中会查询 zvec 的 body text；空 chunk 被丢弃（`filter_usable_chunks`），过期的 sparse id 被清理。
- **Embedder 模块**（`rag/embedder.py`）：HF 环境变量（`HF_ENDPOINT`、`NO_PROXY`）和 `FASTEMBED_CACHE_PATH` 在首次加载模型时惰性设置，而非导入时。使用 hf-mirror.com。
- **主题分配**：逻辑已拆分到 `utils/topic_assigner.py`、`topic_classifier.py`、`topic_file_ops.py`、`topic_pending.py`、`topic_wiki_manager.py`。新增主题相关逻辑应放在这一组模块中，而不是继续膨胀 handler。
- **`IGNORED_DIRS`**（`constants.py`）：小写匹配集合 `{"ai", "noteai", ".noteai", ".NoteAI", "wiki", "ai wiki", "ai-wiki", "ai_wiki", "aiwiki"}`。
- **WIKI.md 操作**：生产写入应通过 `sidecar/wiki_utils.py`；底层解析/CRUD 辅助函数保留在 `utils/wiki_manager.py` 和 `utils/topic_wiki_manager.py`。
- **API key 存储**：三级优先级：环境变量 > OS keyring > Fernet 加密文件（`api_key.dat`，位于 `~/Library/Application Support/NoteAI/`）。Fallback 文件使用 PBKDF2 派生密钥与每安装随机 salt，这属于混淆而非强加密。
- **RAG 端点**没有额外的速率限制，仅受 LLM 信号量约束。

---

## 6. NoteAI 通用 AI 行为规范

以下规则适用于 NoteAI 内置 AI 功能（自动分类、标签提取、知识问答、综述生成等），作用于所有工作区。

### 6.1 标签规则

- 标签从文章内容自动提取（jieba 分词 + 词频）。
- 标签应具备实际分类意义，避免过于泛化的词。
- 优先使用中文标签。
- 每篇文章建议 2-5 个标签。

### 6.2 知识架构（三层）

```
Notes/        ← 原始笔记（Markdown，不可变来源）
wiki/         ← AI 编译的结构化知识（综述、WIKI.md 索引）
Raw/          ← 原始文件归档（PDF、DOCX、PPTX、图片等）
```

- **Notes**：采集的文章，按主题分文件夹。文件标题 = 文件名 stem。
- **wiki**：AI 生成的产物。WIKI.md 仅含主题标题 + 文件列表。综述按主题存放。
- **Raw**：非 Markdown 格式文件的归档区。

### 6.3 AI 功能行为准则

1. **自动分类**：以当前工作区 `wiki/GUIDE.md` 中定义的主题归类规则为准。不确定则标记 pending。
2. **标签提取**：从标题和正文提取有区分度的关键词，避免通用词。
3. **综述生成**：针对二级主题，综合该主题下所有笔记内容。
4. **知识问答**：优先从知识库检索，结合工作区的主题体系给出回答。
5. **级联更新**：新资料入库时，主动检查并更新受影响的已有综述和 WIKI 条目。

### 6.4 文件命名规范

- 文件名 = 文章标题。
- 中文命名优先。
- 避免特殊字符（`/ \ : * ? " < > |`）。
- 综述文件：`{主题名}_综述.md`。

### 6.5 主题存储格式（所有工作区通用）

- YAML frontmatter：`topic: 一级 > 二级 > 三级`。
- 文件系统：`Notes/一级/二级/三级/文件名.md`。
- 分隔符：` > `。
- 最多三层，三级下不再设子题。

### 6.6 两层记忆体系

NoteAI 有两层 Memory，均与工作区绑定（切换工作区即切换画像与对话记忆）：

#### L1：用户画像（工作区级）

位置：`<工作区>/.ai_memory/user_profile.json`（含 `profile_md` 字段）。

- 用户身份、偏好、知识背景。
- 由设置界面的「用户画像」功能维护。
- RAG 对话可读取并用于查询改写。

#### L2：工作区 Memory（RAG 会话）

位置：`<工作区>/.noteai/memory/`。

- 该工作区的 RAG 对话记忆。
- 工作区特定的 AI 运行时数据。

#### 工作区运行时目录

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

---

## 7. 项目记忆

- **`webui/js/`**：vanilla JS IIFE 模块挂载在 `window.*`，无 bundler，无虚拟 DOM。状态放在 `window.AppState` 和 `window.state`。`main.mjs` 是唯一的 ES module。
- **Tauri sidecar**：配置在 `src-tauri/tauri.conf.json`。Python 二进制通过 `python/main.py` → `sidecar.server.main()` 解析。
- **测试覆盖**：约 30+ 单元测试模块 + `tests/integration/test_sidecar_contracts.py`；发布前运行 `uv run pytest`。
- **Prompts**：Python 常量放在 `prompts/`，同时支持 `prompts/yaml/`（loader 兼容两者）。
- **Sidecar Python**：开发使用项目 `.venv`；发布可通过 `scripts/bundle_sidecar_python.sh` 打包到 `src-tauri/resources/sidecar-python`，或设置 `NOTEAI_PYTHON`。
- **`rag_enabled`**：默认 `True`（`config/app_config.py`）。关闭时使用 `sidecar/classic_retriever.py` 进行传统检索。
