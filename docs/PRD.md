# NoteAI PRD — AI 原生个人知识库

**版本**：v2.2  
**日期**：2026-06-21  
**状态说明**：本文档以当前代码库（Tauri + Python sidecar + `webui/`）为准，区分「已实现」「部分实现」「规划中」。与 [README.md](../README.md) 路线图一致。

---

## 1. 产品定位

**一句话**：本地优先的 AI 知识编译器——把零散资料整理成可检索、可演进、按主题组织的 Markdown 知识库。

灵感来自 Karpathy LLM Wiki：

> Stop re-deriving, start compiling.

与一次性 RAG 问答的区别：NoteAI 在工作区中持久化 **Notes（源）→ wiki（编译层）→ Raw（归档）**，并由 AI 辅助分类、综述、链接与检索。当前阶段仍以 **批处理 + 事件触发** 为主，尚未达到「全自动持续编译」的理想态。

**目标用户**：深度知识工作者——研究员、产品经理、工程师、写作者。

**运行形态**：桌面应用（Tauri v2），非纯浏览器站点；功能验证须在 `python run.py` / `cargo tauri dev` 下进行。

---

## 2. 系统架构

### 2.1 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 桌面壳 | Tauri v2 (Rust) | 加载 `webui/`，`invoke` 转发 RPC |
| 前端 | HTML / CSS / 原生 JS | IIFE 模块 + 唯一 ES 模块 `main.mjs`；Tiptap、marked、PDF.js、D3 |
| 后端 | Python 3.10+ sidecar | stdin/stdout **JSON-RPC**，`RpcRouter` 分发 |
| 向量索引 | zvec + fastembed | 稠密：`bge-small-zh-v1.5`（512d）；HNSW + 倒排 |
| 稀疏检索 | jieba TF-IDF | 与稠密混合权重约 0.7 / 0.3 |
| 重排 | FlagReranker | `bge-reranker-v2-m3` |
| LLM | OpenAI 兼容 API | 经 `utils/llm_utils`，并发信号量 4 |

**通信链**：

```
webui (window.api) → Tauri Rust → Python sidecar → Handler → 文件系统 / zvec / LLM
```

进度与流式结果通过 RPC `event`（`progress`、`cascade_survey_chunk`、`cascade_done` 等）推送到前端。

### 2.2 Sidecar 模块（已实现 RPC）

| Handler | 职责摘要 |
|---------|----------|
| `WorkspaceHandler` | 工作区路径、文件树、选中文件、操作日志刷新 |
| `TransferHandler` | 网页下载、导入、格式转换、`auto_convert_pending`、笔记整合 |
| `FilesHandler` | 预览、保存、删除、在 Finder 中显示；保存后可触发级联综述 |
| `TopicsHandler` | 主题树、自动/批量分类、移动、pending、活动日志、综述开关 |
| `TagsHandler` | 标签列表、自动打标、TAGS.md 维护 |
| `LinksHandler` | 双向链接发现、确认/拒绝、统计 |
| `IntelHandler` | AI 改写（流式）、全文搜索 |
| `IntelTopicHandler` | 主题分析、综述生成/应用建议 |
| `RagHandler` | 索引初始化、分块增删、RAG 对话（含 actions 变体）、清空记忆 |
| `CliAgentHandler` | 列出 CLI agent、派发任务、生成 vault `AGENTS.md` |
| `ConfigHandler` | API/UI 配置、主题、用户画像、项目规则 |
| `CloudSyncHandler` | 多云盘认证、推拉、状态（**实验性**） |

主题三层扩展路由注册在 `TopicsHandler.register_routes_3tier`（`get_topic_tree_3tier`、`get_graph_data` 等）。

### 2.3 工作区数据模型

```
<工作区>/
├── Notes/                 # 原始笔记 Markdown（按主题文件夹，最多三级）
│   └── {一级}/{二级}/{三级}/文章.md
├── wiki/                  # AI 编译层
│   ├── WIKI.md            # 主题索引（与 Notes 文件夹结构同步）
│   ├── log.md             # 级联变更日志（按日分组，见 §3.8）
│   └── {主题}_综述.md     # 主题综述（叶名命名，平铺在 wiki 或子路径）
├── Raw/                   # 非 MD 原件归档；自动转换扫描会跳过 Raw/ 内文件
├── .noteai/               # 工作区运行时（常量 WORKSPACE_APP_FOLDER）
│   ├── memory/            # RAG 会话记忆
│   ├── rag_index/         # zvec 向量索引
│   └── ingest_state.json 等运行时状态
├── .ai_memory/            # 用户画像 JSON、项目规则 Markdown
│   ├── user_profile.json
│   └── project_rules.md
├── .pending_topics.json   # 待确认主题分类
└── .links.json            # 待确认双向链接
```

**系统级配置目录**（非工作区）：`~/Library/Application Support/NoteAI/`（macOS）— `workspace_state.json`、`api_config.json`（Fernet 加密字段）等。

**Frontmatter 约定**：`topic: 一级 > 二级 > 三级`（分隔符 ` > `，最多三层）。

**文件监视**：watchdog，约 3s 防抖；忽略 dot 目录、`wiki/`、以及 `IGNORED_DIRS` 中列出的别名；支持 `.md/.txt/.pdf/.docx/.pptx/.html/.doc/.ppt` 等后缀。

> **文档与代码差异**：README 中「NoteAI/」为便于理解的别名；运行时目录名为 **`.noteai`**。用户画像实际路径为 **`<工作区>/.ai_memory/user_profile.json`**，非项目根 `NoteAI/profile.md`。

### 2.4 记忆与规范

| 层级 | 实际路径 | 作用 |
|------|----------|------|
| L1 用户画像 | `<工作区>/.ai_memory/user_profile.json` | 身份、偏好、`profile_md`；RAG 可读取 |
| L2 工作区 Memory | `<工作区>/.noteai/memory/` | 当前工作区对话记忆 |
| 项目规则 | `<工作区>/.ai_memory/project_rules.md` | 设置中「项目规则」读写 |
| 提示词 | `prompts/`（Python 常量） | 分类、综述、级联、云同步等；YAML 迁移停滞 |

---

## 3. 已实现功能（按用户旅程）

### 3.1 工作区与导航

- 首次/切换工作区：创建 `Notes/`、`wiki/`、`Raw/`、`.noteai/{memory,logs,rag_index}`。
- **Tolaria 式四栏布局**：
  - **文件夹侧栏**：仅显示文件夹层级；点击文件夹时中间列表显示该文件夹下的直接子文件。
  - **笔记列表**：默认显示所有笔记；选中文件夹时筛选为该文件夹的直接文件；可拖拽 1px 扁平分隔线调整宽度。
  - **编辑器**：Tiptap WYSIWYG，自动保存。
  - **检查器（Inspector）**：AI 对话 / 文件属性 / 反向链接，三标签切换。
- 主题树（扁平 + 三层）、关系图谱（笔记 / 主题 / 标签 / 链接，D3 力导向）。
- 全文搜索（工作区内标题与正文）。
- 标题栏 **待办** 视图：聚合 `get_all_pending`（主题 pending + 链接 pending）。

### 3.2 采集与格式转换

| 能力 | 说明 |
|------|------|
| 网页下载 | URL → Markdown（`start_web_download`） |
| 文件导入 | 复制到 `Raw/` 后批量转换（`import_files` + `start_file_conversion`） |
| **自动转换** | 打开工作区 + 文件变更后调用 `auto_convert_pending`；扫描支持格式，**跳过 `Raw/` 下已有归档** |
| 笔记整合 | `start_note_integration`（多笔记合并流程） |

支持 PDF / DOCX / PPTX / HTML 等 → Markdown（`modules/file_converter`）。

### 3.3 主题与分类

- AI 单篇 / 批量主题分配（`auto_assign_topic`、`batch_auto_assign_topics`）。
- 手动创建/重命名/删除主题、移动文件、解析 pending（`resolve_topic`）。
- 启动时 `sync_wiki_with_files`：WIKI.md 与 `Notes/` 文件夹对齐。
- 重复主题合并（`merge_duplicate_topics`）。
- 综述开关与状态（`toggle_survey`、`get_survey_status`）。

不确定分类写入 `.pending_topics.json`，由待办 UI 确认。

### 3.4 标签

- jieba 词频提取 + `auto_tag_files`。
- `TAGS.md` 维护、创建/重命名/删除标签。

### 3.5 双向链接

- 本地粗筛 + LLM 精判，结果进入 pending。
- 确认/拒绝单条或全部（`confirm_link`、`reject_link`、`confirm_all_links`）。
- 反向链接查询、链接统计。

### 3.6 阅读、预览与编辑

| 类型 | 行为 |
|------|------|
| `.md` | Tiptap 所见即所得（`tiptap-bundle.js` 须在 `main.mjs` 之前加载）；自动保存 |
| PDF | PDF.js 分页预览 |
| DOCX | mammoth → HTML 只读预览；旧 `.doc` 经转换器 |
| 其他 | 按 `file_preview` 类型回退（文本、图片等） |

**AI 改写**：选中内容流式改写（`llm_rewrite_stream`），对比后应用（`llm_rewrite_apply`）。

### 3.7 小忆助手（意图路由 + RAG）

小忆助手是 NoteAI 的 AI 对话入口，由 `sidecar/handlers/rag_handler.py` 统一接收 `rag_chat`，通过 **意图路由** 决定回答路径，分流到 **无检索回答 / 联网搜索 / RAG 检索** 三条管线。所有对话受 `_rag_chat_lock` 串行化，避免并发污染会话记忆。

> **范围说明**：小忆助手只负责知识问答（chat / general / web / workspace / unknown）。需要执行文件操作（移动笔记、创建主题、跑综述等）时，请使用独立的 **CLI agent 对话界面**（见 §3.8），由第三方 CLI agent（Claude Code / OpenCode 等）直接操作 vault。

#### 3.7.1 意图路由（`sidecar/intent_router.py`）

`classify_intent(question, history)` 返回 `{intent, confidence, reason}`，采用 **两阶段分类**：

**阶段一：启发式关键词匹配（免 LLM 调用）**

按固定顺序短路返回，命中即返回，避免无谓的 LLM 调用：

| 顺序 | 意图 | 匹配规则 | confidence |
|------|------|----------|-----------|
| 1 | `chat` | 前缀匹配问候语：`你好 / 您好 / 哈喽 / 嗨 / hello / hi / 在吗 / 谢谢 / 辛苦了 / 再见 / 拜拜`；或整句等于上述词 | high |
| 2 | `workspace` | 包含关键词：`我的笔记 / 工作区 / 笔记里 / 笔记中 / 我记的 / 我记录 / 主题 / 标签 / 某篇文章 / 某个文件 / 这篇文件 / 这篇文章 / notes/ / wiki/ / guide.md` | high |
| 3 | `web` | 包含关键词：`上网查 / 搜索网络 / 搜一下 / 最新新闻 / 今天天气 / 股价 / 行情 / twitter / x.com / 微博 / 知乎` | medium |

> 关键词均做小写归一化匹配；`workspace` 优先于 `web`，避免「把这篇笔记移到 X 主题」被误判为 `web`。操作类请求（移动/创建/归档等）不再由小忆助手处理，请使用 CLI agent 对话界面。

**阶段二：LLM 分类（启发式未命中时）**

- 先 `check_api_config()` 检查 API 可用性，不可用直接回退 `workspace`（confidence=low）。
- 调用 `INTENT_ROUTER_PROMPT`（`prompts/intent_router.py`），`temperature=0.1`、`max_tokens=120`，要求模型返回 JSON `{intent, confidence, reason}`。
- 解析容错：支持 ```` ```json ``` ```` 包裹、正则提取 `{...}`；解析失败回退 `workspace`。
- `intent` 必须在 `_INTENT_ORDER = (chat, general, workspace, web, unknown)` 中，否则降级为 `unknown`。

**分发逻辑**（`rag_handler._do_rag_chat_inner`）：

| 意图 | 分发方法 | 是否检索 |
|------|----------|---------|
| `chat` / `general` | `_answer_without_retrieval(intent=...)` | 否 |
| `web` | `_answer_without_retrieval(intent="web")` | 联网搜索 |
| `workspace` / `unknown` | `_answer_with_rag` | 向量 RAG |

#### 3.7.2 web 意图：联网搜索（`sidecar/rag/web_search.py`）

`_answer_without_retrieval(intent="web")` 调用 `search_and_fetch(question, max_pages=2)`：

1. **搜索引擎回退链**：`web_search()` 先调 `duckduckgo_search()`，无结果再回退 `baidu_search()`。两者均返回最多 `MAX_RESULTS=5` 条 `{title, url, snippet}`。
2. **SSRF 防护**：`_is_safe_url()` 拦截 localhost、私有 IP（10/8、172.16/12、192.168/16）、链路本地（169.254/16）、环回地址；请求前后均校验。
3. **页面正文抓取**：`search_and_fetch()` 用 `ThreadPoolExecutor(max_workers=max_pages)` 并行抓取页面，`readability` 提取正文 + `markdownify` 转 Markdown，每页截断 `MAX_CONTENT_CHARS=2000` 字符。
4. **上下文组装**：将 web 结果拼成 `[1] 标题\nURL\n正文` 格式，注入 `RAG_ASSISTANT_WEB_PROMPT`，LLM 流式回答。
5. **失败兜底**：搜索异常时 `web_context="未搜索到有效结果。"`，仍走 LLM 回答。

#### 3.7.3 RAG 检索流水线（workspace / unknown 意图）

`_answer_with_rag` 调用 `retriever.retrieve(query, topics, tags)`，核心流程（`sidecar/rag/retriever.py`）：

```
用户提问
  ├─ [查询缓存命中] → 直接返回（TTL 5 分钟，max_size=50）
  ├─ encode_query（bge-small-zh-v1.5 稠密 512d + jieba TF-IDF 稀疏权重）
  ├─ 并行启动 profile 改写（_rewrite_profile，作为 fallback 备用）
  ├─ zvec hybrid_search（dense 0.7 + sparse 0.3，top_k=5 或 7）
  ├─ [条件 HyDE] 原始 top1 score < 0.33 时触发
  │   └─ LLM 生成假设答案 → encode_query → hybrid_search → 合并去重 → 取 top_k
  ├─ [profile fallback] 主搜索无结果且 profile_query ≠ 原查询时
  │   └─ 用 profile 改写后的查询重新 hybrid_search
  ├─ 截断到 _MMR_CANDIDATE_CAP=10
  ├─ MMR 去重（λ=0.5，top_k=5）
  ├─ [条件 rerank] top1 score < _SKIP_RERANK_SCORE=0.75 时
  │   └─ FlagReranker（bge-reranker-v2-m3，fp16，batch=64）重排，取 _RERANK_CANDIDATE_CAP=6
  ├─ filter_usable_chunks（过滤空正文块）
  ├─ context_expand（主题综述 + 1-hop 反链扩展）
  └─ filter_usable_chunks → 返回
```

**关键阈值与参数**：

| 常量 | 值 | 作用 |
|------|----|----|
| `DEFAULT_TOP_K` | 5 | 默认返回块数 |
| `SEARCH_TOP_K_TAGS` | 7 | 带主题/标签过滤时扩大召回 |
| `HYDE_TRIGGER_BELOW_SCORE` | 0.33 | 原始得分低于此值才触发 HyDE（避免每次都调 LLM） |
| `_MMR_CANDIDATE_CAP` | 10 | MMR 候选上限 |
| `_RERANK_CANDIDATE_CAP` | 6 | rerank 候选上限 |
| `_SKIP_RERANK_SCORE` | 0.75 | top1 得分 ≥ 此值时跳过 rerank |
| `_query_cache` | TTL=300s, max=50 | 查询缓存 |
| `_RETRIEVE_EXECUTOR` | max_workers=2 | 检索线程池 |

**reranker 降级**：`_get_reranker()` 首次加载失败（FlagEmbedding 未安装）时 `_RERANKER_DISABLED=True`，后续直接返回纯向量得分排序；可通过环境变量 `NOTEAI_DISABLE_RERANKER=1` 主动禁用。

**上下文组装**（`_answer_with_rag`）：

- **当前文件优先**：`current_file` 参数指向的文件作为 `[0]` 引用注入上下文（截断 4000 字符），模型可显式引用。
- 其余检索结果按 `[1] [2] ...` 编号注入，每条带 `source_label`。
- 同一 `file_path` 去重，避免重复注入。
- 注入 `RAG_CHAT_PROMPT`，LLM 流式回答（`temperature=0.3`），完成后返回 `citations` 列表。

#### 3.7.4 context_expand 检索扩展（`sidecar/rag/context_expand.py`）

在向量检索结果基础上，前置 **主题综述** + 后置 **1-hop 确认反链**，提供更完整的上下文：

| 扩展类型 | 数量上限 | 单条字符上限 | score | source_type |
|---------|---------|-------------|-------|-----------|
| 主题综述 | `_MAX_SURVEY_TOPICS=2` | `_MAX_SURVEY_CHARS=2800` | 0.95 | `survey` |
| 1-hop 反链 | `_MAX_BACKLINK_FILES=4` | `_MAX_BACKLINK_CHARS=700` | `_BACKLINK_SCORE=0.25` | `backlink` |

- **主题综述**：从检索结果的 `topic` 字段提取主题键，读取 `wiki/{主题}_综述.md`（经 `get_survey_path`），解析 frontmatter 后取正文，超长截断加 `…`。
- **1-hop 反链**：通过 `utils/link_indexer.load_links()` 加载已确认链接（`status=="confirmed"`），对每个 seed 文件找邻居文件；优先用已索引的 chunk（`fetch_chunks_by_file`，limit=1），无索引时读文件正文截断。
- **去重**：按 `id` 去重，综述在前、向量命中在中、反链在后。
- **空结果兜底**：向量检索无结果时，仅返回主题综述（若存在）。

#### 3.7.6 两层记忆体系

| 层级 | 路径 | 内容 | 更新时机 |
|------|------|------|---------|
| **L1 用户画像** | `<工作区>/.ai_memory/user_profile.json` | `identity`（职业/专业领域/兴趣/学习目标）、`preferences`、`behavior.frequent_topics`、`raw_facts`、`profile_md` | 每轮对话后 `update_profile_from_message`；索引构建后 `update_profile_from_topics`（取前 20 个主题） |
| **L2 RAG 会话记忆** | `<工作区>/.noteai/memory/` | `long_memory.json`（用户长期信息，上限 1500 字符）、`short_memory.json`（近期对话摘要） | 每轮对话后 `update_long_memory` + `save_short_memory` |

**L1 画像写入**（`rag/profile.py`）：

- `extract_structured_info(message)` 调用 `PROFILE_EXTRACT_PROMPT`，LLM 返回 JSON（职业/专业领域/兴趣/学习目标/facts）。
- 字段合并策略：`expertise_areas` / `interests` / `learning_goals` 用集合并集合并；`raw_facts` 追加并保留最近 50 条。
- `profile_md` 优先于结构化字段：`get_profile_summary()` 优先返回 `profile_md`（+ 近期关注主题），否则从 `identity` 拼接。

**L1 查询改写**（`rewrite_query_with_profile`）：

- 取 `identity.interests` + `behavior.frequent_topics`（前 5 个）作为 `context_hints`。
- 返回 `f"{query}（用户关注领域：{hints_str}）"`，作为 RAG 检索的 fallback 查询（仅当主搜索无结果时使用）。

**L2 记忆写入**（`rag/memory.py`）：

- `update_long_memory(user_message)`：先调 `update_profile_from_message`（L1），再用 `USER_INFO_EXTRACT_PROMPT` 提取用户信息，追加到 long_memory；超过 `_MAX_LONG_MEMORY_CHARS=1500` 时用 `LONG_MEMORY_COMPRESS_PROMPT` 压缩。
- `update_short_memory(chat_history)`：将完整对话历史用 `MEMORY_COMPRESS_PROMPT` 压缩后保存。
- **迁移**：`_migrate_legacy_memory()` 一次性将旧 `.ai_memory/long_memory.json` / `short_memory.json` 迁移到 `.noteai/memory/`。

**记忆注入**（`build_memory_section`）：每轮 RAG 对话时组装 `[用户画像] + [关于用户的长期记忆] + [近期对话摘要]` 注入系统提示词。

#### 3.7.6 辅助机制

- **历史压缩**（`_extractive_compress`）：jieba 关键词提取（topK=3）+ 首尾句拼接（首句 60 字 + 尾句 60 字），无 jieba 时退化为前 800 字符截断。
- **错误冷却**：`_record_error` 写入 `<工作区>/.noteai/rag_index/error_state.json`（含时间戳）；`_check_error_reset` 在 `config.rag_error_cooldown_seconds` 内直接拒绝请求并返回 `[冷却] {错误信息}`；成功后 `_clear_error_reset` 清除状态。
- **保存建议**：`parse_save_suggestion(answer)` 解析 LLM 回答中的保存建议标记，前端展示「保存为笔记」按钮。
- **流式推送**：`_send_chat_chunk` 通过 `rag_chat_chunk` 事件推送 token；`_finish_chat` 推送 `rag_chat_done`（含 answer、citations、suggest_save_note）。

#### 3.7.7 RPC 接口

| RPC | 说明 |
|-----|------|
| `init_rag_index` / `rag_rebuild_index` | 构建 / 重建索引（支持增量，`_rag_build_lock` 防并发） |
| `rag_add_chunks` / `rag_remove_chunks` | 增量增删（与文件监视联动） |
| `rag_chat` | RAG 对话入口（仅知识问答，不执行文件操作） |
| `rag_clear_memory` | 清空 L2 short_memory |
| `rag_index_status` | 索引状态（chunk 数、文件数、构建进度、是否构建中） |

**事件类型**：`rag-index-progress`、`rag_chat_chunk`、`rag_chat_done`、`rag_error`、`rag_index_built`。

> `rag_chat_with_actions` RPC 已移除（原为 `rag_chat` 别名）。文件操作请使用 CLI agent 对话界面（§3.8）。

### 3.8 CLI Agent 对话界面（独立于小忆助手）

CLI agent 对话界面是 NoteAI 中 **执行文件操作的入口**，与小忆助手（§3.7，仅知识问答）分离。用户在此界面选择已安装的 CLI agent（Claude Code / OpenCode / Codex / Gemini），以自然语言下达操作指令，agent 直接以工作区为工作目录操作 vault。

**定位**：小忆助手回答「是什么 / 为什么」类知识问题；CLI agent 对话界面执行「移动 / 创建 / 整理 / 归档」类操作。两者不共享意图路由，CLI agent 界面不经过 `classify_intent`。

**实现**（`sidecar/cli_agent_runner.py` + `sidecar/handlers/cli_agent_handler.py` + `sidecar/vault_agents_md.py`）：

| 能力 | 说明 |
|------|------|
| 列出 agent | `list_cli_agents` 返回 claude / opencode / codex / gemini 的安装状态（`shutil.which`） |
| 派发任务 | `run_cli_agent` 以 workspace 为 cwd 启动子进程（`subprocess.Popen`），stdout 流式回传 |
| Vault 指南 | `generate_vault_agents_md` 生成 `<workspace>/AGENTS.md`，描述三层架构、主题体系、笔记规范、AI 行为准则 |
| 事件类型 | `cli_agent_start` / `cli_agent_output` / `cli_agent_done` / `cli_agent_error` |

**agent 命令配置**（`SUPPORTED_AGENTS`）：

| agent | 命令 | 参数模板 |
|-------|------|---------|
| claude | `claude` | `-p {prompt} --include-directories {workspace}` |
| opencode | `opencode` | `run {prompt}` |
| codex | `codex` | `--prompt {prompt}` |
| gemini | `gemini` | `-p {prompt}` |

**运行机制**：

1. 用户在 CLI agent 对话界面选择 agent + 输入指令。
2. `_cli_agent_lock` 串行化（同一时刻只运行一个 agent 任务）。
3. `run_cli_agent()` 构建 `full_cmd`，`subprocess.Popen(cwd=workspace, env={NO_COLOR:1})` 启动。
4. 逐行读取 stdout，通过 `cli_agent_output` 事件流式推送到前端。
5. 进程结束（`return_code==0` 成功）推送 `cli_agent_done`；非零退出码推送 `cli_agent_error`。

**AGENTS.md 作用**：CLI agent 启动后会读取工作区根目录的 `AGENTS.md`，理解 vault 的三层架构（Notes/wiki/Raw）、主题体系（`一级 > 二级 > 三级`）、frontmatter 规范、综述命名规则等，从而正确地操作文件。

> **已知限制**（规划改进）：
> - 无默认 agent 选择逻辑（需用户每次手动选择）
> - 无 agent 选择记忆（不持久化上次选择）
> - 无取消运行中 agent 的机制（`_current_process` 已定义但未使用）
> - agent 写操作依赖 watchdog 触发级联，时序不可控
> - 无安全沙箱（agent 可任意读写工作区文件）

### 3.9 综述与级联更新（部分闭环）

**已实现**：

- 按主题生成/更新 `wiki/*_综述.md`（`ai_topic_survey`、级联模块 `sidecar/cascade.py`）。
- 触发场景：主题解析、文件移入主题、Ingest/Lint 级联、手动重试；失败队列可重试（待办「综述失败」）。
- 变更写入 **`wiki/log.md`**；前端 `cascade_survey_chunk` / `cascade_done`。
- **Ingest 统一任务条**：转换 → 分类 → 索引 → 综述 → Lint → WIKI 同步（可取消/重试）。

**未实现**：Karpathy 式「单源触及 10–15 页」的全自动交叉引用网。

### 3.10 记录与日志

| 文件 | 内容 |
|------|------|
| `.noteai/log.md` | ~~已废弃~~ → 见 `wiki/log.md`；旧 `.noteai/activity_log.json` 打开工作区时自动迁移 |
| `wiki/log.md` | **统一变更日志**（入库、转换、分类、级联、Lint、问答归档） |
| UI「操作记录」 | 设置 → 操作记录，`get_activity_log` 读 `wiki/log.md` |

二者已合并为 **`wiki/log.md`**（Karpathy 式按日条目）；旧 `.noteai/activity_log.json` 在打开工作区时自动迁移。

### 3.11 云盘同步（实验性）

- 提供商：OneDrive、百度、阿里云、腾讯云 COS、123 盘、坚果云 WebDAV、iCloud（`python/sidecar/cloud/providers/`）。
- RPC：`cloud_sync_*` 系列；前端 **设置 → 云盘同步**（`webui/js/cloud-sync.js`）。
- **产品状态**：默认隐藏（设置 → 界面 → 启用云盘同步实验）；冲突策略未产品化。

### 3.12 配置与安全

- API Key 优先级：**环境变量 > OS keyring > Fernet 加密 `api_config.json`**。
- UI 配置、明暗主题、连接测试。
- CI：`pytest` + GitHub Actions（`main`、`LangChain2` 及 PR）。

---

## 4. 部分实现与已知限制

| 项 | 现状 |
|----|------|
| 编译模式 | Ingest 统一流水线 + 事件触发级联；非 7×24 持续守护 |
| WIKI.md | **每主题一行摘要**（综述/首段摘录）+ 文件列表 |
| Query → Archive | 笔记 / wiki / **追加综述**（LLM 合并） |
| Lint | 健康检查 + 入库末尾；**自动删断链、自动更新过时综述** |
| 检索扩展 | 向量 + 已确认反链 1-hop + 主题综述（`context_expand`） |
| schema.md | 顶层规范 + 向导 + 设置页编辑；运行时校验写权限/主题层级 |
| 交叉引用 | 保存后本地启发式建议 → pending；全库 AI 发现仍走「发现链接」 |
| 转换失败 | `.noteai/convert_failures.json` + 待办重试 |
| RAG actions | `rag_chat_with_actions` 已等同于 `rag_chat`（无 LLM 代码执行，安全） |
| 稀疏检索 | 空正文块在 `hybrid_search` 中过滤并清理陈旧 sparse id |
| RAG 默认 | `rag_enabled=true`；关闭时用主题树 + 全文 + wiki（`classic_retriever`） |
| 分发 Python | 发行包需自带解释器或 `NOTEAI_PYTHON`；见 `scripts/bundle_sidecar_python.sh` |
| 前端布局 | Tolaria 式四栏布局已落地；移动端/小屏适配待完善 |
| CLI agent | 已支持 claude / opencode / codex / gemini；agent 安装与权限由用户环境决定 |
| 测试覆盖 | 30+ 单元测试模块 + 1 个 sidecar 集成契约测试（`pytest` 约 250+） |
| 文档别名 | README/AGENTS 中 `NoteAI/`、`NoteAI/profile.md` 与代码路径不一致 |

---

## 5. 与 Karpathy 理想模型对照

| 概念 | NoteAI 现状 | 差距 |
|------|-------------|------|
| Raw Sources | `Raw/` 归档 | 缺少「不可变」语义与版本策略 |
| Wiki 编译层 | `wiki/*_综述.md` + 级联更新 | 有触发式更新，无全库联动与交叉引用网 |
| Schema | `project_rules.md` + `prompts/` | 无统一 `schema.md` |
| Ingest | 八阶段可恢复流水线（convert→…→lint→sync） | 非 7×24 持续守护 |
| Query → Archive | 笔记 / wiki / 追加综述 | 非全自动 wiki 页沉淀 |
| Lint | 断链/孤儿/过时综述 + 自动修复 | 需打开应用触发 |
| index 摘要 | WIKI.md 每主题 `>` 摘要行 | 与 Karpathy 一行摘要仍有风格差 |
| log | `wiki/log.md` 按日分组 | 旧 `.noteai` 日志可迁移 |

**结论**：P0/P1 闭环已落地；距离「持续自我维护的编译器」仍差 **Raw 版本语义、全自动交叉引用网、7×24 守护**。

---

## 6. 功能路线图

与 [README.md §路线图](../README.md) 对齐。

### P0 — 产品闭环（已交付）

| 项 | 说明 | 状态 |
|----|------|------|
| 级联增强 | 入库/Lint 触发综述；失败队列 + 待办重试 | ✅ |
| Ingest 进度 | 单一任务条（可取消/重试） | ✅ |
| Query → Archive | 笔记 / wiki / 追加综述 | ✅ |
| Lint | 断链/孤儿/过时综述 + 自动修复 | ✅ |
| schema.md | 向导 + 设置编辑 + 运行时校验 | ✅ |

### P1 — 体验与智能

| 项 | 说明 | 状态 |
|----|------|------|
| 保存时交叉引用 | 保存 MD 后本地启发式 → pending | ✅ 首版 |
| 搜索增强 | 主题/标签过滤、预览高亮 | ✅ 首版 |
| WIKI 摘要索引 | 每主题 `>` 摘要行 | ✅ |
| 转换可感知 | 失败队列 + 待办重试 | ✅ |
| 云盘同步 | 实验开关，默认隐藏 | ✅ |
| 检索扩展 | 向量 + 反链 1-hop + 综述 | ✅（已有） |
| Karpathy 交叉引用网 | 单源 8–15 页自动建链（保存/入库触发） | ✅ |
| Tolaria 式四栏布局 | 文件夹侧栏 / 笔记列表 / 编辑器 / Inspector | ✅ |
| CLI Agent 桥接 | Claude Code / OpenCode / Codex / Gemini + `AGENTS.md` | ✅ |

### P2 — Agent 化

| 项 | 说明 | 状态 |
|----|------|------|
| Agent 助手 | 结构化工具：搜文件、列主题、移笔记、跑综述 | ✅ 首版 |
| 多源采集 | RSS / 转录 → Notes/_采集 | ✅ 首版 |
| Personal Memory | 对话后自动提炼进 L1 user_profile | ✅ |
| Raw 批量重转 | `convert_raw_archive` RPC | ✅ |
| CLI agent 生态 | 更多 CLI agent、MCP server、vault 内工具调用 | 规划中 |

（原 P2 列表保留为方向说明：Agent 型助手、RSS/剪藏/转录、L1 Memory 升级。）

### P3 — 生态

- 本地模型（Ollama 等）。
- 移动端只读 + 同步。
- 发布导出、协作空间。

### 优先级（开发排序）

1. P0：schema.md → Ingest UI → 级联可靠性 → Lint → Query→Archive  
2. P1：交叉引用、搜索、WIKI 摘要、云同步决策  
3. P2：Agent、多源采集、Memory 升级  
4. P3：Local AI、移动端、发布

---

## 7. 非功能需求

| 类别 | 要求 |
|------|------|
| 隐私 | 默认本地；API Key 不落库明文；云同步凭证走 keyring/加密配置 |
| 性能 | LLM 并发上限 4；大文件转换/索引后台任务，不阻塞 RPC 主线程 |
| 可靠性 | 工作区路径校验；删除主题级联警告；zvec 删除前先查询 chunk |
| 可维护性 | 新 RPC 须注册 `src-tauri/src/rpc.rs` 白名单；集成测试见 `tests/integration/test_sidecar_contracts.py` |
| 兼容性 | macOS 为主开发平台；Windows/Linux 路径与 keyring 行为需单独验证 |

---

## 8. 成功指标（目标态）

| 指标 | 目标 |
|------|------|
| 编译覆盖率 | 有综述的活跃主题占比 > 80% |
| 交叉引用密度 | 平均每篇 Notes 至少 1 条已确认出链 |
| Lint 健康度 | 断链/过时/孤儿占比 < 5% |
| 对话归档率 | 满意回答存档操作 > 20%（功能上线后统计） |
| 周活跃 | 深度用户每周使用 ≥ 4 天 |

当前版本 **不以** 上表作为发布门禁，仅作 v2.x 演进方向。

---

## 9. 附录：关键 RPC 索引

<details>
<summary>展开 RPC 列表（开发参考）</summary>

**工作区**：`get_workspace_status`, `set_workspace_path`, `get_workspace_tree`, `on_file_selected`, `refresh_log`

**传输**：`start_web_download`, `import_files`, `start_file_conversion`, `auto_convert_pending`, `extract_topics`, `start_note_integration`

**文件**：`get_file_preview`, `save_file_content`, `read_file_raw`, `delete_file`, `reveal_in_finder`

**主题**：`get_topic_tree`, `auto_assign_topic`, `batch_auto_assign_topics`, `move_file_to_topic`, `get_all_pending`, `get_activity_log`, `get_topic_tree_3tier`, `get_graph_data`, …

**标签**：`get_all_tags`, `auto_tag_files`, `create_tag`, `rename_tag`, `delete_tag`

**链接**：`discover_links`, `get_backlinks`, `confirm_link`, `reject_link`, …

**智能**：`llm_rewrite`, `llm_rewrite_stream`, `search_files`, `ai_topic_survey`, …

**RAG**：`init_rag_index`, `rag_chat`, `rag_chat_with_actions`, `rag_clear_memory`

**CLI agent**：`list_cli_agents`, `run_cli_agent`, `generate_vault_agents_md`

**云同步**：`cloud_sync_list_providers`, `cloud_sync_auth`, `cloud_sync_push`, `cloud_sync_pull`, …

**配置**：`get_api_config`, `save_api_config`, `get_user_profile`, `save_user_profile`, `get_project_rules`, …

</details>

---

*维护说明：实现变更时请同步更新 §2–§4；路线图以 README 与本文 §6 为准，避免三处漂移。*
