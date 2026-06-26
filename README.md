<img width="720" height="441" alt="NoteAI" src="https://github.com/user-attachments/assets/d36bc718-227e-468a-a6b0-45b1eae35ae3" />

# 🧠 NoteAI

**English** · **[中文](#中文)** · [📋 PRD](./docs/PRD.md)

---

<a id="english"></a>

## English

**AI-native personal knowledge base desktop app** — collect sources, compile knowledge, discover links, and chat with **Xiao Yi** (小忆) grounded in your workspace.

> **Stop re-deriving, start compiling.**  
> Inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6a6bf555914893e9891c11519de94f) — not one-off RAG, but knowledge **compiled into wiki** that compounds over time.

### 💡 Why NoteAI?

📝 Obsidian for notes + 💬 Claude for Q&A = two silos. Every chat starts from zero; insights rarely flow back into your library.

NoteAI unifies **capture → organize → research → Q&A** in one desktop app:

| You do | NoteAI helps |
|--------|----------------|
| 📥 Drop PDFs / web pages / Word files | 🔄 Auto-convert to Markdown, archive originals in `Raw/` |
| 📂 Skip folder planning | 🏷️ AI suggests topics & tags — you confirm |
| 📚 Topics keep growing | 📑 Auto-generate & cascade-update topic surveys |
| ❓ Ask a question | 🤖 Xiao Yi searches your notes & surveys first |

### ✨ Highlights

- 🖥️ **Native desktop** — Tauri v2 + Python sidecar; local workspace, your data
- 📐 **Tolaria-style four-pane layout** — Folder sidebar · Note list · Editor · Inspector with AI / Properties / Backlinks tabs
- ✍️ **WYSIWYG** — Tiptap Markdown editor; in-app PDF / DOCX preview
- 🔄 **Ingest pipeline** — convert → compile → classify → index → crossref → cascade → lint → sync (resumable)
- 🕸️ **Knowledge graph** — topics, tags, bidirectional links (force-directed)
- 🤖 **Xiao Yi assistant** — HyDE + hybrid search + rerank; Q&A mode vs Agent mode
- 🔌 **CLI agent bridge** — dispatch Claude Code / OpenCode / Codex / Gemini into your vault with auto-generated `AGENTS.md`
- 📬 **Unified inbox** — pending topics, links, survey failures, Lint issues in one place
- 📊 **Health metrics** — survey coverage, avg outbound links, Lint count

### 🚀 Quick Start

**Requires**: Python 3.10+ · Rust · [Tauri CLI v2](https://v2.tauri.app/) · [uv](https://docs.astral.sh/uv/) recommended

```bash
git clone https://github.com/Miles128/NoteAI.git
cd NoteAI
uv sync
python run.py
```

`run.py` checks deps and runs `cargo tauri dev` (Python sidecar included). First build bundles the Tiptap editor.

**Four steps**

1. 📂 **Open a workspace** — any local folder
2. ⚙️ **Settings → Model** — LLM API key (OpenAI-compatible)
3. 📄 **Import sources** — PDF / DOCX, web download, or file import
4. 💬 **Open Xiao Yi** — ask questions or browse notes & graph

### 🧩 Features

#### 📐 Layout & Navigation (Tolaria-aligned)

| Feature | Description |
|---------|-------------|
| 📁 Folder sidebar | Show folders only; click to filter note list |
| 📄 Note list | All notes by default; folder's direct files when selected |
| ✍️ Editor | Tiptap WYSIWYG with autosave |
| 🔍 Inspector | AI chat / file properties / backlinks, three tabs |
| ↔️ Resizers | 1px flat dividers; drag to resize sidebar & note list |

#### 📥 Capture & Convert

| Feature | Description |
|---------|-------------|
| 🌐 Web download | Batch URLs → Markdown (WeChat, Zhihu, etc.) |
| 📄 Format conversion | PDF / DOCX / PPTX / HTML / TXT → Markdown |
| 🔄 Auto-convert | Scan on workspace changes (5s debounce); originals → `Raw/` |
| ✨ Note compile | LLM strips headers/footers, neutral tone, searchable body |
| 📥 Import files | Copy to `Raw/` → convert in background |

#### 🗂️ Organize & Topics

| Feature | Description |
|---------|-------------|
| 📁 3-tier topics | `L1 > L2 > L3` → `Notes/` folders + frontmatter |
| 🏷️ Auto tags | jieba + TF-IDF; 2–5 distinctive Chinese tags |
| 🧠 Topic suggestions | LLM proposes new / merged topics |
| 📚 WIKI index | `wiki/WIKI.md` + `{topic}_survey.md` |
| 📋 schema.md | Workspace rules: AI write scope, topic levels, conflicts |

#### 🔗 Links & Graph

| Feature | Description |
|---------|-------------|
| ↔️ Bidirectional links | Local filter + AI relevance; pending / confirmed |
| 🕸️ Relation graph | Notes, topics, tags, links |
| 🔍 Full-text search | Titles & body across workspace |

#### ✍️ Read & Edit

| Feature | Description |
|---------|-------------|
| 📝 Markdown | Tiptap WYSIWYG, autosave |
| 👁️ Preview | PDF pages; DOCX layout preview |
| 🪄 AI rewrite | Stream rewrite selection, diff & apply |
| 📑 Topic surveys | Read all notes in a topic; generate / cascade update |

#### 🤖 Xiao Yi Assistant

| Mode | Capabilities |
|------|----------------|
| 💬 **Q&A mode** (default) | RAG over notes & surveys; **search notes** & **list topics** without Agent mode |
| 🛠️ **Agent mode** | Also **create topics**, **move notes**, **refresh surveys**, **trigger ingest** |

Agent mode notes:

- 🆕 **Create topic** — L1 or L2; for L2 you must **explicitly name the L1 parent** — no auto-guessing
- 💾 **Save answers** — to `Notes/小忆对话/`, `wiki/`, or append to topic survey
- 🧠 **User profile** — Settings → Xiao Yi, Markdown background & preferences

**Retrieval**: query → HyDE → Milvus Lite hybrid (dense 0.7 + sparse 0.3) → rerank → MMR → streaming LLM

#### 🔌 CLI Agent Bridge

| Feature | Description |
|---------|-------------|
| 🛠️ Agent selector | Pick Claude Code / OpenCode / Codex / Gemini from the AI panel |
| 📤 Dispatch | Send prompts to the chosen CLI agent with workspace as cwd |
| 📋 Auto AGENTS.md | Generate `AGENTS.md` describing vault structure for CLI agents |
| 📡 Stream events | Live output via `cli_agent_output` / `cli_agent_done` / `cli_agent_error` |

#### ☁️ Cloud sync (experimental)

Enable in Settings → UI → experimental; WebDAV, Jianguoyun, Aliyun, Tencent, OneDrive, Baidu Pan, etc.

### 📂 Workspace Layout

```
<workspace>/
├── Notes/              # 📓 Raw notes (Markdown, by topic)
├── wiki/               # 📚 Compiled: WIKI.md, surveys, log.md
├── Raw/                # 📦 Originals (PDF, DOCX, …)
├── schema.md           # 📋 AI rules (Schema wizard)
├── .noteai/            # ⚙️ Runtime: memory/, rag_index/, ingest state…
└── .ai_memory/         # 👤 User profile, project rules
```

> Some docs say `NoteAI/`; code uses **`.noteai/`** (legacy name).

### 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  🦀 Tauri v2 (Rust)                                                   │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │  webui/                                                         │   │
│  │  Folder Sidebar · Note List · Editor · Inspector (AI/Prop/Backlinks) │   │
│  └────────────────────────────────┬──────────────────────────────┘   │
│                                   │ invoke → JSON-RPC                  │
│  ┌────────────────────────────────▼──────────────────────────────┐   │
│  │  🐍 Python sidecar                                               │   │
│  │  Handlers · RAG · ingest · CLI agent bridge · cloud sync         │   │
│  └───────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**Ingest pipeline**

```
schema → convert → compile → classify → index → crossref → cascade → lint → sync
```

### 🛠️ Tech Stack

| Layer | Stack |
|-------|--------|
| 🦀 Shell | Tauri v2, Rust |
| 🎨 Frontend | HTML / CSS / vanilla JS, Tiptap, D3, PDF.js |
| 🐍 Backend | Python 3.10+ sidecar, JSON-RPC |
| 🧬 RAG | Milvus Lite, fastembed (bge-small-zh), FlagReranker |
| 📑 Docs | PyMuPDF, mammoth, html2text |
| 🇨🇳 Chinese NLP | jieba |
| 📦 Deps | uv · `pyproject.toml` |

### 📁 Repo Layout

```
NoteAI/
├── run.py              # 🚀 Dev launcher
├── src-tauri/          # 🦀 Tauri app
├── webui/              # 🎨 Frontend
├── python/sidecar/     # 🐍 RPC, handlers, RAG, ingest
├── modules/            # 📥 Download, convert, preview
├── utils/              # 🔧 LLM, topics, links, logging
├── prompts/            # 💬 Prompts
├── config/             # ⚙️ Config
└── tests/              # 🧪 Tests
```

### 🧪 Dev & Test

```bash
uv sync --extra dev
pytest
```

See [docs/PRD.md](./docs/PRD.md) for product details & roadmap.

### 🗺️ Roadmap

Aligned with [docs/PRD.md](./docs/PRD.md) — evolve from batch tool to **continuous knowledge compiler**.

| Priority | Focus |
|----------|--------|
| 🔥 P0 | Cascade updates · ingest progress & resume · query→archive · Lint · schema.md |
| 🟡 P1 | Cross-ref on save · search UX · WIKI summaries · cloud sync GA |
| 🎨 P1 | Main-area state machine · unified inbox · clickable citations · onboarding |
| 🟢 P2 | Contradiction detection · graph + editor coexist · Vite bundle (later) |

### 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](./CONTRIBUTING.md) to get started.

- Report Bugs: [Issue Tracker](https://github.com/Miles128/NoteAI/issues)
- Submit PRs: [Pull Requests](https://github.com/Miles128/NoteAI/pulls)

### 👤 Author & License

**Sihai (四海)** · [MIT License](./LICENSE)

---

<a id="中文"></a>

## 中文

**AI 原生的个人知识库桌面应用** — 采集资料、编译知识、发现关联，用「小忆」从你的笔记里回答问题。

> **Stop re-deriving, start compiling.**  
> 灵感来自 [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6a6bf555914893e9891c11519de94f) — 不只临时 RAG，而是把知识**编译进 wiki**，持续增值。

### 💡 为什么需要 NoteAI？

📝 Obsidian 记笔记 + 💬 Claude 查资料 — 仍是两套系统：每次提问要从零解释背景，聊完的洞见也很难回到库里。

NoteAI 把 **采集 → 整理 → 研究 → 问答** 放进同一款桌面应用：

| 你做的事 | NoteAI 帮你做的 |
|---------|----------------|
| 📥 丢进 PDF / 网页 / Word | 🔄 自动转 Markdown、归档到 `Raw/` |
| 📂 不想先想文件夹 | 🏷️ AI 建议主题与标签，待你确认 |
| 📚 主题越积越多 | 📑 自动生成 / 级联更新主题综述 |
| ❓ 想问一个问题 | 🤖 小忆先查你的笔记与综述，再回答 |

### ✨ 核心亮点

- 🖥️ **桌面原生** — Tauri v2 + Python sidecar，工作区在本地，数据在你手里
- 📐 **Tolaria 式四栏布局** — 文件夹侧栏 · 笔记列表 · 编辑器 · 检查器（AI / 属性 / 反链）
- ✍️ **所见即所得** — Tiptap 编辑 Markdown；PDF / DOCX 应用内预览
- 🔄 **自动入库流水线** — 转换 → 编译 → 分类 → 索引 → 交叉引用 → 综述 → 健康检查（可断点续跑）
- 🕸️ **知识图谱** — 主题、标签、双向链接力导向可视化
- 🤖 **小忆助手** — HyDE + 混合检索 + 重排序；问答模式 / 助手模式双档
- 🔌 **CLI agent 桥接** — 在 vault 内调用 Claude Code / OpenCode / Codex / Gemini，自动生成 `AGENTS.md`
- 📬 **统一待处理** — 待分类、待确认链接、综述失败、Lint 问题一处搞定
- 📊 **健康度指标** — 综述覆盖率、均链数、Lint 问题数一目了然

### 🚀 快速开始

**环境**：Python 3.10+ · Rust · [Tauri CLI v2](https://v2.tauri.app/) · 推荐 [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/Miles128/NoteAI.git
cd NoteAI
uv sync
python run.py
```

`run.py` 检查依赖并启动 `cargo tauri dev`（含 Python sidecar）。首次构建会打包 Tiptap 编辑器。

**四步上手**

1. 📂 **打开工作区** — 任意本地文件夹
2. ⚙️ **设置 → 模型** — 配置 LLM API Key（OpenAI 兼容接口）
3. 📄 **导入资料** — 拖入 PDF / DOCX，或用网页下载、导入文件
4. 💬 **打开小忆助手** — 侧栏提问，或浏览笔记与知识图谱

### 🧩 功能一览

#### 📐 布局与导航（对标 Tolaria）

| 功能 | 说明 |
|------|------|
| 📁 文件夹侧栏 | 仅显示文件夹；点击筛选中间笔记列表 |
| 📄 笔记列表 | 默认展示所有笔记；选中文件夹后仅显示该文件夹直接子文件 |
| ✍️ 编辑器 | Tiptap 所见即所得，自动保存 |
| 🔍 检查器 | AI 对话 / 文件属性 / 反向链接，三栏切换 |
| ↔️ 分隔线 | 1px 扁平分隔，可拖拽调整侧栏与笔记列表宽度 |

#### 📥 采集与转换

| 功能 | 说明 |
|------|------|
| 🌐 网页下载 | 批量 URL → Markdown（公众号、知乎等优化） |
| 📄 格式转换 | PDF / DOCX / PPTX / HTML / TXT → Markdown |
| 🔄 自动转换 | 工作区变更后自动扫描转换（5s 防抖），原件进 `Raw/` |
| ✨ 笔记编译 | LLM 去页眉页脚、统一语气，产出可检索的正文 |
| 📥 导入文件 | 选文件 → 复制到 `Raw/` → 后台立即转换 |

#### 🗂️ 整理与主题

| 功能 | 说明 |
|------|------|
| 📁 三级主题 | `一级 > 二级 > 三级`，对应 `Notes/` 目录与 frontmatter |
| 🏷️ 自动标签 | jieba 分词 + 词频，2–5 个有区分度的中文标签 |
| 🧠 主题建议 | LLM 分析结构，建议新建 / 合并主题 |
| 📚 WIKI 索引 | 自动维护 `wiki/WIKI.md` 与 `{主题}_综述.md` |
| 📋 schema.md | 工作区规范：AI 可写范围、主题层级、冲突策略 |

#### 🔗 链接与图谱

| 功能 | 说明 |
|------|------|
| ↔️ 双向链接 | 本地粗筛 + AI 精判；待确认 / 已确认 |
| 🕸️ 关系图谱 | 笔记、主题、标签、链接力导向图 |
| 🔍 全文搜索 | 工作区内标题与正文检索 |

#### ✍️ 阅读与编辑

| 功能 | 说明 |
|------|------|
| 📝 Markdown 编辑 | Tiptap 所见即所得，自动保存 |
| 👁️ 多格式预览 | PDF 分页；DOCX 排版预览 |
| 🪄 AI 改写 | 流式改写选中段落，对比后应用 |
| 📑 主题综述 | 通读主题下笔记，生成 / 级联更新综述 |

#### 🤖 小忆助手

| 模式 | 能做什么 |
|------|----------|
| 💬 **问答模式**（默认） | RAG 检索笔记与综述；**搜索笔记**、**查看主题列表**（无需开助手模式） |
| 🛠️ **助手模式** | 在上述基础上可 **新建主题**、**移动笔记**、**更新综述**、**触发入库整理** |

助手模式要点：

- 🆕 **新建主题** — 支持一级 / 二级；建二级时须你**明确说出**所属一级，小忆不会自动猜测挂靠
- 💾 **存为笔记** — 优质回答可存到 `Notes/小忆对话/` 或 `wiki/`，或追加到主题综述
- 🧠 **用户画像** — 设置 → 小忆助手，Markdown 描述背景与偏好

**检索链路**：提问 → HyDE → Milvus Lite 混合检索（稠密 0.7 + 稀疏 0.3）→ 重排序 → MMR → LLM 流式输出

#### 🔌 CLI Agent 桥接

| 功能 | 说明 |
|------|------|
| 🛠️ Agent 选择器 | 在 AI 面板切换 Claude Code / OpenCode / Codex / Gemini |
| 📤 任务派发 | 以工作区为 cwd，向所选 CLI agent 发送提示词 |
| 📋 自动生成 AGENTS.md | 描述 vault 结构、主题体系、笔记规范，供外部 agent 读取 |
| 📡 流式事件 | 通过 `cli_agent_output` / `cli_agent_done` / `cli_agent_error` 实时展示 |

#### ☁️ 云盘同步（实验性）

设置 → 界面 → 启用实验功能后，可配置 WebDAV / 坚果云、阿里云、腾讯云、 OneDrive、百度网盘等。

### 📂 工作区结构

```
<你的工作区>/
├── Notes/              # 📓 原始笔记（Markdown，按主题分文件夹）
├── wiki/               # 📚 AI 编译层：WIKI.md、主题综述、log.md
├── Raw/                # 📦 原件归档（PDF、DOCX、PPTX…）
├── schema.md           # 📋 工作区 AI 规范（Schema 向导生成）
├── .noteai/            # ⚙️ 运行时：memory/、rag_index/、ingest 状态…
└── .ai_memory/         # 👤 用户画像、项目规则
```

> 文档中偶见 `NoteAI/` 目录名，代码里对应 **`.noteai/`**（历史称呼）。

### 🏗️ 架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  🦀 Tauri v2（Rust）                                                    │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │  webui/                                                         │   │
│  │  文件夹侧栏 · 笔记列表 · 编辑器 · 检查器（AI/属性/反链）              │   │
│  └────────────────────────────────┬──────────────────────────────┘   │
│                                   │ invoke → JSON-RPC                  │
│  ┌────────────────────────────────▼──────────────────────────────┐   │
│  │  🐍 Python sidecar                                               │   │
│  │  Handlers · RAG · 入库流水线 · CLI agent 桥接 · 云同步             │   │
│  └───────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**入库流水线（Ingest）**

```
schema → convert → compile → classify → index → crossref → cascade → lint → sync
         转换      笔记编译    分类      向量索引   交叉引用    综述     健康检查
```

### 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| 🦀 桌面壳 | Tauri v2、Rust |
| 🎨 前端 | HTML / CSS / 原生 JS、Tiptap、D3、PDF.js |
| 🐍 后端 | Python 3.10+ sidecar、JSON-RPC |
| 🧬 RAG | Milvus Lite、fastembed（bge-small-zh）、FlagReranker |
| 📑 文档 | PyMuPDF、mammoth、html2text |
| 🇨🇳 中文 | jieba 分词 / TF-IDF |
| 📦 包管理 | uv · `pyproject.toml` |

### 📁 项目结构

```
NoteAI/
├── run.py              # 🚀 开发启动（Tauri dev + sidecar）
├── src-tauri/          # 🦀 Tauri 应用
├── webui/              # 🎨 前端
├── python/sidecar/     # 🐍 RPC 服务、handlers、RAG、入库
├── modules/            # 📥 下载、转换、预览
├── utils/              # 🔧 LLM、主题、链接、日志
├── prompts/            # 💬 提示词
├── config/             # ⚙️ 配置
└── tests/              # 🧪 测试
```

### 🧪 开发与测试

```bash
uv sync --extra dev
pytest
```

更多产品细节与路线图 → [docs/PRD.md](./docs/PRD.md)

### 🗺️ 路线图

与 [docs/PRD.md](./docs/PRD.md) 对齐 — 从「批处理工具」进化为 **持续维护的知识编译器**。

| 优先级 | 方向 |
|--------|------|
| 🔥 P0 | 级联更新 · Ingest 进度与断点续跑 · Query→Archive · Lint · schema.md |
| 🟡 P1 | 保存时交叉引用 · 搜索增强 · WIKI 摘要索引 · 云盘产品化 |
| 🎨 P1 | 主区域状态机 · 统一待处理 · 小忆引用可点击 · 首次引导 |
| 🟢 P2 | 矛盾检测 · 图谱与编辑并存 · 前端 Vite 打包（不急） |

### 🤝 贡献

欢迎贡献！请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解如何参与。

- 报告 Bug: [Issue Tracker](https://github.com/Miles128/NoteAI/issues)
- 提交 PR: [Pull Requests](https://github.com/Miles128/NoteAI/pulls)

### 👤 作者与许可

**四海** · [MIT License](./LICENSE)
