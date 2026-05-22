# NoteAI PRD — AI 原生个人知识库

**版本**：v2.1  
**日期**：2026-05-20  
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
| 向量索引 | Milvus Lite + fastembed | 稠密：`bge-small-zh-v1.5`（512d） |
| 稀疏检索 | jieba TF-IDF | 与稠密混合权重约 0.7 / 0.3 |
| 重排 | FlagReranker | `bge-reranker-v2-m3` |
| LLM | OpenAI 兼容 API | 经 `utils/llm_utils`，并发信号量 4 |

**通信链**：

```
webui (window.api) → Tauri Rust → Python sidecar → Handler → 文件系统 / Milvus / LLM
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
│   ├── rag_index/         # Milvus Lite 数据
│   └── log.md             # 自动化操作记录（HTML 注释嵌入 JSON）
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
- 侧栏文件树：映射 **Notes / wiki / Raw** 三区。
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

### 3.7 小忆助手（RAG）

流水线：

```
用户提问 → HyDE 查询扩展 → Milvus 混合检索 → 主题/标签过滤
         → FlagReranker 重排 → MMR 去重 → LLM 流式回答
```

- 工作区索引：`init_rag_index`、`rag_add_chunks` / `rag_remove_chunks`（与文件监视联动）。
- `rag_chat` / `rag_chat_with_actions`（后者含 **可执行代码动作**，存在注入风险，见 §5）。
- `rag_clear_memory` 清空 L2 记忆。

### 3.8 综述与级联更新（部分闭环）

**已实现**：

- 按主题生成/更新 `wiki/*_综述.md`（`ai_topic_survey`、级联模块 `sidecar/cascade.py`）。
- 触发场景包括：文件保存、主题解析、文件移入主题、手动综述任务等（后台 `cascade_update_*` 任务）。
- 变更写入 **`wiki/log.md`**（按日期 `## YYYY-MM-DD` + 时间戳条目）。
- 前端可接收 `cascade_survey_chunk` / `cascade_done` 事件。

**未实现**：Karpathy 式「单源触及 10–15 页」的全自动交叉引用网；Ingest 无统一任务条。

### 3.9 记录与日志

| 文件 | 内容 |
|------|------|
| `.noteai/log.md` | 转换、打标、移动等自动化操作（`utils/activity_log`，HTML 注释存 JSON） |
| `wiki/log.md` | 级联/综述相关变更（`append_changelog`） |
| UI「记录」 | `get_activity_log` 展示上述自动化记录 |

二者并存，尚未合并为单一 Karpathy 规范 `log.md`。

### 3.10 云盘同步（实验性）

- 提供商：OneDrive、百度、阿里云、腾讯云 COS、123 盘、坚果云 WebDAV、iCloud（`python/sidecar/cloud/providers/`）。
- RPC：`cloud_sync_*` 系列；前端 **设置 → 云盘同步**（`webui/js/cloud-sync.js`）。
- **产品状态**：能力在开发中，错误处理与冲突策略未产品化；路线图 P1 决定「正式化或隐藏入口」。

### 3.11 配置与安全

- API Key 优先级：**环境变量 > OS keyring > Fernet 加密 `api_config.json`**。
- UI 配置、明暗主题、连接测试。
- CI：`pytest` + GitHub Actions（`main`、`LangChain2` 及 PR）。

---

## 4. 部分实现与已知限制

| 项 | 现状 |
|----|------|
| 编译模式 | 综述/索引多为 **事件触发批处理**，非 7×24 持续 Ingest |
| WIKI.md | 以 **目录/文件列表** 为主，非「每主题一行摘要」 |
| Query → Archive | 小忆「保存到 wiki」已支持 |
| Lint | 入库末尾自动检查；无一键批量修复 |
| 检索扩展 | 已确认反链 1-hop + 主题综述注入；非 Graph RAG |
| schema.md | 无顶层 LLM 行为规范文件；`project_rules.md` 仅覆盖部分场景 |
| 交叉引用 | 链接 pending 存在，**保存时自动建链** 未做 |
| RAG actions | `rag_chat_with_actions` 可执行 LLM 生成代码 — **安全风险** |
| 稀疏检索 | 仅稀疏命中时 `content`/`file_path` 可能为空，影响回答质量 |
| 前端布局 | `body { zoom }` 与 flex 组合可能导致侧栏/预览异常（多字号需 Tauri 回归） |
| 测试覆盖 | 约十余个测试文件，**无 handler/RAG 单元全覆盖**（~个位数百分比） |
| 文档别名 | README/AGENTS 中 `NoteAI/`、`NoteAI/profile.md` 与代码路径不一致 |

---

## 5. 与 Karpathy 理想模型对照

| 概念 | NoteAI 现状 | 差距 |
|------|-------------|------|
| Raw Sources | `Raw/` 归档 | 缺少「不可变」语义与版本策略 |
| Wiki 编译层 | `wiki/*_综述.md` + 级联更新 | 有触发式更新，无全库联动与交叉引用网 |
| Schema | `project_rules.md` + `prompts/` | 无统一 `schema.md` |
| Ingest | 转换 + 分类 + 索引 + 综述 | 步骤分散，无统一进度/可取消流水线 |
| Query → Archive | RAG 对话 | 未沉淀为 wiki 页 |
| Lint | — | 未实现 |
| index 摘要 | WIKI.md | 目录索引，非一行摘要 |
| log | 双日志（`.noteai` + `wiki`） | 格式未完全 Karpathy 化 |

**结论**：已具备「本地知识库 + AI 整理 + RAG」核心路径；距离「持续自我维护的编译器」仍差 **统一 Ingest、Lint、归档闭环、Schema** 四块。

---

## 6. 功能路线图

与 [README.md §路线图](../README.md) 对齐。

### P0 — 产品闭环（下一版重点）

| 项 | 说明 |
|----|------|
| 级联增强 | 新资料入库后可靠刷新所有受影响综述与 WIKI；失败可重试 |
| Ingest 进度 | 转换 → 分类 → 索引 → 综述 **单一任务条**（可取消、可重试） |
| Query → Archive | 小忆助手「保存到 wiki / 追加综述」 |
| Lint 首版 | 断链、孤儿页、源已改综述未更新 |
| schema.md | 工作区顶层：frontmatter、AI 可写范围、冲突策略 |

### P1 — 体验与智能

| 项 | 说明 |
|----|------|
| 保存时交叉引用 | 写入 MD 后异步建议链接，接入 pending |
| 搜索增强 | 跳转预览、高亮、主题/标签过滤 |
| WIKI 摘要索引 | 每主题一行摘要 |
| 转换可感知 | 失败进收件箱；`Raw/` 遗留支持重新转换 |
| 云盘同步 | 产品化或隐藏实验入口 |
| 检索扩展 | 向量检索 + 已确认反链 1-hop + 主题综述注入（替代完整 Graph RAG） |

### P2 — Agent 化

- Agent 型助手（搜文件、建主题、跑综述流水线）。
- RSS / 剪藏 / 转录等多源采集。
- Personal Memory 从对话自动提炼进 L1。

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
| 可靠性 | 工作区路径校验；删除主题级联警告；Milvus 删除前先查询 chunk |
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

**云同步**：`cloud_sync_list_providers`, `cloud_sync_auth`, `cloud_sync_push`, `cloud_sync_pull`, …

**配置**：`get_api_config`, `save_api_config`, `get_user_profile`, `save_user_profile`, `get_project_rules`, …

</details>

---

*维护说明：实现变更时请同步更新 §2–§4；路线图以 README 与本文 §6 为准，避免三处漂移。*
