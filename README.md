<img width="720" height="441" alt="NoteAI" src="https://github.com/user-attachments/assets/d36bc718-227e-468a-a6b0-45b1eae35ae3" />

# NoteAI

**AI 驱动的个人知识库桌面应用** — 采集资料、编译知识、发现关联，并用「小忆」助手基于你的工作区回答问题。

[English](./README_EN.md) · [📖 详细文档](./docs/README.md)

---

## 💡 它解决什么问题

灵感来自 [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：

> **Stop re-deriving, start compiling.**

普通 RAG 每次提问都从原始笔记临时检索、临时拼凑。NoteAI 在中间加一层 **由 AI 维护的结构化知识（wiki 综述、索引、双链）**，让信息「编译一次、持续增值」；同时内置 **RAG 对话助手**，回答时优先引用你自己的资料。

---

## ✨ 亮点

- 🖥️ **桌面原生**：Tauri v2 + Python sidecar，本地工作区，数据在你手里
- ✍️ **所见即所得**：Markdown 用 Tiptap 直接排版编辑；PDF / DOCX 可在应用内预览
- 🔄 **自动转笔记**：工作区内 PDF / DOCX / PPTX 等会在启动与文件变更后自动转为 Markdown（无需每次手动点转换）
- 🕸️ **知识图谱**：主题、标签、双向链接力导向可视化
- 💬 **可对话**：HyDE + 混合检索 + 重排序，流式问答，带短期/长期记忆
- 📥 **可扩展采集**：网页下载、手动批量转换、自动主题/标签

---

## 🚀 快速开始

**环境**：Python 3.10+、Rust、[Tauri CLI v2](https://v2.tauri.app/)，推荐 [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/Miles128/NoteAI.git
cd NoteAI
uv sync
python run.py
```

`run.py` 会检查依赖并启动 `cargo tauri dev`（同时拉起 Python sidecar）。首次构建会执行 `npm run build:tiptap` 打包编辑器资源。

1. 📂 在应用中 **打开工作区**（任意文件夹）
2. ⚙️ 在 **设置** 中配置 LLM API Key（支持 OpenAI 兼容接口）
3. 📄 将 PDF / DOCX 等放入工作区（**不要只放在 `Raw/` 根目录里指望自动转**，见下方说明），或走「导入文件」
4. 🤖 从侧栏浏览笔记，打开 **小忆助手** 开始对话

---

## 🧩 功能概览

### 📥 采集与导入

| 功能 | 说明 |
|------|------|
| 🌐 网页下载 | 批量 URL → Markdown，针对公众号、知乎等优化 |
| 📄 格式转换 | PDF / DOCX / PPTX / HTML / TXT → Markdown；「转换」页可选手动批量 |
| 🔄 **自动转换** | 打开工作区后、以及监听到文件变更（约 3s 防抖）时，自动扫描并转换支持的格式 → 生成 `Notes/` 下 Markdown，原文件归档到 `Raw/` |
| 📥 导入文件 | 选择文件 → 复制到 `Raw/` → 后台立即 `convert_batch`，无需再点转换按钮 |
| ✨ AI 排版 | 可选 LLM 清理版式、标题与列表 |

**自动转换范围（实现说明）**

- 扫描整个工作区中支持的后缀（与 `FileConverterManager` 一致）
- **跳过** 路径已在 `Raw/` 下的文件（避免对归档重复处理）
- 因此：新文件请放在工作区根目录、`Notes/` 外层级等；若只拷贝进 `Raw/` 且未走「导入」，需用「转换」页或挪出 `Raw/` 后再触发自动转换

### 🗂️ 整理与索引

| 功能 | 说明 |
|------|------|
| 📁 三级主题 | `一级 > 二级 > 三级`，对应 `Notes/` 目录与 frontmatter |
| 🏷️ 标签 | jieba 分词 + 词频自动打标 |
| 🧠 主题建议 | LLM 分析现有结构，建议新建/合并主题 |
| 📚 WIKI 索引 | 自动维护 `wiki/WIKI.md` 与主题综述 |

### 🔗 链接与图谱

| 功能 | 说明 |
|------|------|
| ↔️ 双向链接 | 本地粗筛 + AI 精判，待确认/已确认状态 |
| 🕸️ 关系图谱 | 笔记、主题、标签、链接的力导向图 |
| 🔍 全文搜索 | 工作区内标题与正文检索 |

### ✍️ 阅读与编辑

| 功能 | 说明 |
|------|------|
| 📝 Markdown | Tiptap 所见即所得编辑，自动保存 |
| 👁️ 预览 | PDF 分页浏览；DOCX 排版预览（mammoth，只读） |
| 🪄 AI 改写 | 流式改写选中内容，对比后应用 |
| 📑 主题综述 | 按主题生成/更新 `wiki/*_综述.md` |

### 🤖 小忆助手（RAG）

| 功能 | 说明 |
|------|------|
| 💡 知识库问答 | 基于当前工作区向量索引 |
| 🔎 检索链路 | HyDE → Milvus Lite 混合检索 → FlagReranker → MMR → LLM 流式输出 |
| 🧠 记忆 | 会话摘要 + 跨会话用户画像（`NoteAI/profile.md`） |

### ☁️ 云盘同步（实验性）

支持将工作区同步到多种云存储（如 WebDAV / 坚果云、阿里云、腾讯云、OneDrive、百度网盘等），在 **设置 → 云盘同步** 中配置。

---

## 📂 工作区结构

```
<你的工作区>/
├── Notes/          # 原始笔记（Markdown，按主题分文件夹）
├── wiki/           # AI 编译层：综述、WIKI.md 索引
├── Raw/            # 原始文件归档（PDF、DOCX、PPTX…）
└── NoteAI/         # 工作区运行时数据
    ├── GUIDE.md    # 主题归类规则
    ├── memory/     # RAG 对话记忆
    ├── logs/
    └── rag_index/  # 向量索引
```

项目根目录另有 **L1 用户画像**：`NoteAI/profile.md`（跨工作区共享）。

---

## 🏗️ 架构

```
┌──────────────────────────────────────────────┐
│  Tauri v2（Rust）                               │
│  ┌────────────────────────────────────────┐  │
│  │  webui/  侧栏 · 编辑器 · 预览 · 图谱 · 助手 │  │
│  └──────────────────┬─────────────────────┘  │
│                     │ invoke → JSON-RPC       │
│  ┌──────────────────▼─────────────────────┐  │
│  │  Python sidecar（stdin/stdout）           │  │
│  │  Handlers: 工作区 · 文件 · 主题 · 标签 · 链接  │  │
│  │           · RAG · 云同步 · 配置 …          │  │
│  │  rag/: 分块 · 嵌入 · Milvus · 检索 · 记忆   │  │
│  └──────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

**⚡ RAG 流水线（简述）**

```
提问 → HyDE 查询扩展 → 稠密+稀疏混合检索 (bge-small-zh)
     → 主题/标签过滤 → bge-reranker 重排 → MMR 去重 → LLM 流式回答
```

---

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| 🦀 桌面壳 | Tauri v2、Rust |
| 🎨 前端 | 原生 HTML/CSS/JS、Tiptap、marked.js、PDF.js、D3 |
| 🐍 后端 | Python 3.10+ sidecar、LangChain |
| 🧬 RAG | Milvus Lite、fastembed、FlagEmbedding |
| 📑 文档 | PyMuPDF、mammoth、python-docx、html2text |
| 🇨🇳 中文 NLP | jieba |
| 📦 依赖 | uv、`pyproject.toml` |

---

## 📁 项目结构

```
NoteAI/
├── run.py              # 开发启动入口（≠ python/main.py sidecar）
├── src-tauri/          # Tauri 应用
├── webui/              # 前端静态资源
├── python/sidecar/     # RPC 服务与业务 handlers
├── modules/            # 下载、转换、预览、整合等
├── utils/              # LLM、主题、链接、日志
├── prompts/            # 提示词
├── config/             # 配置
└── tests/
```

---

## 🧪 开发与测试

```bash
uv sync --extra dev
pytest
```

更细的 API、配置与使用说明见 [docs/README.md](./docs/README.md)。

---

## 🗺️ 路线图

与 [docs/PRD.md](./docs/PRD.md) 对齐，目标是从「批处理工具」升级为 **持续维护的知识编译器**。

### 🔥 产品闭环（P0）

| 方向 | 说明 |
|------|------|
| 级联更新 | 新资料入库后，自动刷新受影响的 `wiki/*_综述.md` 与 WIKI 条目 |
| Ingest 进度 | 转换、分类、索引、综述生成统一任务条（可取消、可重试） |
| Query → Archive | 小忆助手优质回答一键存为 wiki 页或追加综述 |
| Lint 首版 | 断链、孤儿页、源已改但综述未更新 |
| schema.md | 工作区顶层约定：frontmatter、AI 何时可改 wiki、冲突处理 |

### 🟡 体验与智能（P1）

| 方向 | 说明 |
|------|------|
| 保存时交叉引用 | 保存 Markdown 后异步建议双向链接（接入现有 pending 流程） |
| 搜索增强 | 结果跳转预览、命中高亮；按主题/标签过滤 |
| WIKI 摘要索引 | WIKI.md 每主题一行摘要，而不只是文件列表 |
| 转换可感知 | 自动转换进度/失败原因进收件箱；`Raw/` 内遗留文件支持「重新转换」 |
| 云盘同步 | 正式产品化或暂时隐藏入口 |
| 检索扩展 | RAG 自动附带已确认反链与主题 `*_综述.md`（非 Graph RAG 全量建图） |

### 🎨 界面与工程（P1）

| 方向 | 说明 |
|------|------|
| 主区域状态机 | 统一 home / 图谱 / 预览 / 待办 / 设置，避免多处改 `display` 互相遮挡 |
| 侧栏底栏 | 折叠、字号缩放下 dock 区始终可见；统计可点击跳转 |
| 小忆助手 | 回答附可点击引用片段；「存入库」主按钮；宽度持久化 |
| 统一收件箱 | 待分类、待确认链接、转换失败、Lint 项合并展示 |
| 首次引导 | 工作区 → API Key → 示例笔记三步 |

### 🟢 后续（P2）

- 矛盾检测、过时论断、标准化 `log.md`
- 图谱与编辑并存（选中文档时图谱不独占主区）
- 前端 Vite 打包 + TypeScript（**不急于**整仓换 React/Vue）

---

## 👤 作者与许可

**四海** · [MIT License](./LICENSE)
