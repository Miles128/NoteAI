# NoteAI

**AI 驱动的 Markdown 知识库桌面应用** — 采集、整理、链接、洞察，让零散信息生长为结构化知识。

灵感源自 [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：不是每次提问都从原始文档重新检索，而是让 LLM 把零散资料"编译"成持续增值的结构化知识库。

## 核心理念

> **Stop re-deriving, start compiling.**

传统 RAG 每次提问都从原始文档临时翻找、拼凑答案，没有积累。NoteAI 在原始资料和最终答案之间插入一个"编译层"——由 AI 主动维护的结构化 Markdown 知识库。知识编译一次，持续增值，而不是每次重新推导。

## 功能全景

### 📥 采集

| 功能 | 说明 |
|------|------|
| 网页文章下载 | 批量 URL 输入，自动提取正文转 Markdown；针对微信公众号、知乎等平台优化标题提取 |
| 多格式转换 | PDF / DOCX / PPTX / HTML / TXT → Markdown；PDF 自动去重页眉页脚 |
| AI 辅助排版 | LLM 智能格式化，清理乱码，规范化标题与列表 |

### 🗂️ 整理

| 功能 | 说明 |
|------|------|
| 多级主题 | 主题支持无限层级（用 `/` 分隔路径），侧边栏树形展示，预览界面面包屑导航 |
| 标签系统 | jieba 分词 + 词频统计自动打标签；YAML front matter 管理 |
| 笔记整合 | 按主题拼接文件 → LLM 生成整合笔记 → 保存到 Organized 目录 |
| AI 主题分析 | LLM 审视现有主题结构，给出新建/调整/合并建议 |

### 🔗 链接

| 功能 | 说明 |
|------|------|
| 双向链接发现 | 本地粗筛（同主题/共享标签/文件名重叠）→ AI 精判内容相关性 |
| 关系图可视化 | 文件-主题-标签-双链的完整图结构，Canvas 力导向布局 |
| WIKI.md 索引 | 自动生成并维护多级主题目录、文件大纲、来源列表 |

### ✍️ 编辑

| 功能 | 说明 |
|------|------|
| Markdown 编辑器 | Tiptap 富文本 + CodeMirror 6 风格编辑 |
| 实时预览 | marked.js + highlight.js 渲染，编辑/预览双栏模式 |
| AI 改写 | 选中内容 → LLM 流式改写 → 预览对比 → 决定是否应用 |
| 主题综述 | 针对指定主题，LLM 撰写综述文章 |

### 🔍 搜索与浏览

| 功能 | 说明 |
|------|------|
| 全文搜索 | 工作区内大小写不敏感搜索，返回匹配文件、标题、上下文片段 |
| 侧边栏视图 | 文件树 / 主题 / 标签 / 双向链接 四视图切换 |
| 文件预览 | Markdown、TXT、PDF（逐页渲染）、Word 文档 |

## 架构

```
┌─────────────────────────────────────────────┐
│                  Tauri v2 壳                  │
│  ┌─────────────────────────────────────────┐ │
│  │          前端 (HTML/CSS/JS)              │ │
│  │  sidebar · editor · preview · graph     │ │
│  └──────────────┬──────────────────────────┘ │
│                 │ window.api (JSON-RPC)       │
│  ┌──────────────▼──────────────────────────┐ │
│  │        Python Sidecar (stdin/stdout)     │ │
│  │  ┌─────────────────────────────────┐    │ │
│  │  │  SidecarServer (9 Mixins)       │    │ │
│  │  │  Config · Workspace · Transfer  │    │ │
│  │  │  Files · Tags · Topics          │    │ │
│  │  │  Links · Intel · Paths          │    │ │
│  │  └─────────────────────────────────┘    │ │
│  │  modules/ · utils/ · prompts/           │ │
│  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

**三层知识架构**（对齐 Karpathy LLM Wiki）：

```
工作区/
├── Notes/               ← Raw 层：原始 Markdown（不可变，来源真相）
├── Organized/           ← Wiki 层：AI 编译的结构化知识（LLM 拥有，持续更新）
├── Raw/                 ← 原始文件归档（PDF/DOCX/PPTX）
├── WIKI.md              ← 全局索引（多级主题目录 + 文件大纲）
├── tags.md              ← 标签索引（按标签聚合的双链索引）
└── .links.json          ← 双向链接数据（pending / confirmed）
```

## 技术栈

| 类别 | 技术 |
|------|------|
| 桌面壳 | Tauri v2 + Rust |
| 前端 | HTML5 / CSS3 / JS，marked.js，highlight.js，PDF.js，Tiptap |
| 后端 | Python 3.10+，LangChain + LangChain-OpenAI |
| 文档解析 | PyMuPDF, mammoth, python-docx, html2text, readability-lxml |
| NLP | jieba 分词 |
| 文件监听 | watchdog |
| 依赖管理 | uv + pyproject.toml |

## 快速开始

### 环境要求

- **Python 3.10+**
- **Rust** 与 [Tauri CLI v2](https://v2.tauri.app/)
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖

### 安装

```bash
cd NoteAI
uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv sync
```

使用 pip：

```bash
pip install -e .
```

### 运行

```bash
python run.py
```

会检查依赖后执行 `cargo tauri dev`，同时启动 Python sidecar 子进程。

## 目录结构

```
NoteAI/
├── run.py                  # 启动器
├── src-tauri/              # Tauri 壳（Rust）
├── webui/                  # 前端静态资源
│   ├── index.html
│   ├── css/                # variables · layout · components · tree · editor
│   └── js/                 # state · icons · sidebar · tree · topic · tags · links · graph · editor · ...
├── python/
│   ├── main.py             # sidecar 进程入口
│   └── sidecar/            # RPC 路由 + 9 个 Mixin 业务模块
├── modules/                # 业务模块（下载 · 转换 · 整合 · 预览 · 主题提取）
├── utils/                  # 工具库（LLM · 标签 · 链接 · 文本处理 · 日志）
├── prompts/                # LLM 提示词（独立管理，业务代码 import 使用）
├── config/                 # 配置（settings.py + config.json）
├── tests/                  # 测试
└── docs/                   # 文档
```

## 下一步计划

### 🔥 级联更新（Cascade Updates）

新资料进入知识库时，不只创建新页面，还要主动找到并更新所有受影响的已有页面。一篇新论文触发 5 个已有页面的更新——这是 LLM Wiki 的灵魂，没有它知识库就是"只加不改"的死水。

### 🔥 矛盾检测（Contradiction Detection）

Ingest 新资料时，让 LLM 比对新内容与已有 wiki 内容，主动标注冲突。两篇文章说法打架，帮你发现。

### 🔥 Lint 自检

手动触发知识库体检：找矛盾、找过时论断、找断链（相关但未互链的文章）、找空白（被多次引用但没有独立页面的概念）。

### 🟡 操作日志

维护 `wiki/log.md`，记录每次 Ingest/Lint/级联更新的变更内容，追溯知识库的演变历史。

### 🟡 主题拖拽排序

侧边栏主题树支持拖拽调整顺序和层级，拖拽子主题到另一个父主题下自动更新路径前缀。

## 测试

```bash
uv sync --extra dev
pytest
```

## 作者

四海

## 许可证

MIT
