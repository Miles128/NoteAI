<img width="720" height="441" alt="NoteAI" src="https://github.com/user-attachments/assets/d36bc718-227e-468a-a6b0-45b1eae35ae3" />

# 🧠 NoteAI

**[中文](#中文)** · **[English](#english)** · [📋 PRD](./documents/PRD.md)

> **Stop re-deriving, start compiling.**

NoteAI 是本地优先的 AI 原生个人知识工作流桌面应用。它把原始资料编译为**可追溯的语义知识库**，再自动用于整理、检索问答、主题阅读、回顾和输出。

---

<a id="中文"></a>

## 中文

### 产品定位

你负责把资料放进工作区，NoteAI 负责把它们变成可持续维护、可核验、可检索、可回顾的知识资产。

```
采集资料 → 自动整理为 Notes → 语义编译 → 知识库 → 问答 / 回顾 / 输出
```

与“每次提问都重新读一遍笔记”的 RAG 不同，NoteAI 将知识先编译为带来源的语义中间层，再生成面向阅读与查询的视图。`Notes/` 永远是不可变事实来源；语义库和 wiki 都是可重建的派生产物。

### 核心能力

| 能力 | 说明 |
|---|---|
| 全量实体语义知识库 | 自动维护实体、概念、命题、证据与来源；无需日常维护关系图 |
| 命题与证据 | 只收录 `conclusion` / `hypothesis` 类型的知识判断；每条正式命题必须有可定位的 Evidence |
| 主题语义页 | 基于活跃命题与证据生成主题页；假设显式标注，待审冲突不会发布 |
| 精确增量更新 | 文档变化只重编受影响的块、实体、命题、主题状态和页面；失败保留上一版产物 |
| 语义工作台 | 查看当前知识及其来源；自动关系只用于阅读和问答，高影响异常才进入 Inbox |
| 采集与整理 | PDF / DOCX / PPTX / 网页等转换为 Markdown，归档原件，自动分类、标签与主题维护 |
| 知识问答 | HyDE + 混合检索 + 重排序；回答以 Notes 源块为证据，而不是把 Wiki 当作唯一事实来源 |
| 自动物化 | 笔记抽取或实体合并后，自动刷新受影响的实体、概念与主题页；失败保留上一版 |
| 回顾与输出 | 后续支持知识变化摘要、主题简报与将带引用答案保存为笔记或待办 |

### 工作区结构

```text
<workspace>/
├── Notes/                         # 原始笔记：知识事实来源，不由语义编译器改写
├── wiki/
│   ├── WIKI.md                    # 主题索引
│   ├── <主题>_综述.md              # 兼容的主题综述
│   └── semantic/                  # 语义物化视图：主题页、实体知识页等
├── Raw/                           # PDF、DOCX、PPTX 等原件归档
├── .noteai/
│   ├── compiler/semantic.db       # 文档、块、实体、概念、命题、证据、关系、依赖
│   └── rag_index/                 # 派生检索索引，不是语义事实来源
└── .ai_memory/                    # 用户画像与工作区规则
```

### 语义编译模型

```text
Notes → Document → Block → Entity / Concept / Claim → Evidence / Relations
                                              ↓
                                      TopicState → Semantic Wiki / RAG index
```

- **Entity**：人物、组织、产品、模型、协议等全库实体；支持受控类型与别名。
- **Claim**：具有知识判断价值的结论或假设，不把定义、教程、参数说明和普通事实罗列误收为命题。
- **Evidence**：从 Claim 回到具体 Notes 文件、标题路径和稳定文档块的证据边。
- **Materialized views**：实体知识页、主题语义页与综述由语义库派生，随源资料增量更新。

### 快速开始

环境：Python 3.10+、Rust、[Tauri CLI v2](https://v2.tauri.app/)、[uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/Miles128/NoteAI.git
cd NoteAI
uv sync --extra dev --extra rag
uv run python run.py
```

首次使用：打开本地工作区 → 在「设置 → 模型」配置 OpenAI 兼容 LLM → 导入资料 → 在语义工作台运行「编译全部」或等待 Ingest 完成。

### 技术架构

```text
Tauri v2 shell
  └─ webui（原生 HTML / CSS / JavaScript）
       └─ JSON-RPC
            └─ Python sidecar
                 ├─ Ingest / 转换 / 分类 / 链接
                 ├─ Semantic compiler（SQLite SKIR、依赖图、物化）
                 ├─ RAG（zvec + bm25s + rerank）
                 └─ CLI Agent bridge
```

语义编译流水线：

```text
Scan → Normalize → Parse → Semantic Extract → Resolve → Link
     → Topic Reduce → Materialize → Index → Validate → Publish
```

### 开发与测试

```bash
uv sync --extra dev --extra rag
uv run pytest
uv run python run.py
```

详细的产品范围、数据契约、治理边界和验收标准见 [PRD](./documents/PRD.md)。

### 当前边界

- Notes 是源稿；语义库、实体页与 Wiki 均可由它重建。
- RAG 只回答知识问题并提供引用，不执行文件移动、创建或归档。
- 正常使用无需维护实体或关系；只有高影响异常、实体合并和文件操作需要明确人工决定。
- 不建设无证据支撑的“全连接图谱”。Graph RAG 是后续的受控检索增强，答案仍以 Notes 证据为准。
- RSS 仅支持用户手动导入或拉取。

### 贡献

欢迎提交 Issue 和 Pull Request。开始前请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

---

<a id="english"></a>

## English

### What is NoteAI?

NoteAI is a local-first, AI-native personal knowledge workflow desktop app. It compiles source material into a traceable semantic knowledge base, then uses it for organization, grounded Q&A, review, and output.

```text
Capture → organized Notes → semantic compilation → knowledge base → Q&A / review / output
```

`Notes/` remains the immutable source of truth. The semantic database, entity pages, topic pages, summaries, and retrieval indexes are derived, rebuildable views.

### Highlights

- **Complete entity knowledge base** — canonical entity records across the workspace, with aliases, controlled types, mentions, and source provenance.
- **Claims with evidence** — only conclusions and hypotheses become claims; every formal claim is backed by source evidence.
- **Traceable semantic views** — entity knowledge pages and topic semantic pages link back to Notes and stable blocks.
- **Incremental compiler** — changes invalidate only affected semantic objects and views; failed publishes retain the last usable output.
- **Automatic derived views** — affected entity, concept, and topic pages refresh after semantic extraction without per-page publishing.
- **Low-maintenance workflow** — relationships are automatic and traceable; only meaningful exceptions need attention.
- **Local knowledge Q&A** — HyDE, zvec/BM25 hybrid retrieval, reranking, and cited answers grounded in source blocks. Graph RAG is a future, controlled enhancement.

### Quick Start

Requires Python 3.10+, Rust, [Tauri CLI v2](https://v2.tauri.app/), and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Miles128/NoteAI.git
cd NoteAI
uv sync --extra dev --extra rag
uv run python run.py
```

Run the full test suite with `uv run pytest`. See the [PRD](./documents/PRD.md) for the product contract and acceptance criteria.

### License

**Sihai (四海)** · [MIT License](./LICENSE)
