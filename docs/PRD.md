# NoteAI PRD — AI 原生个人知识库 v2.0

## 1. 产品定位与愿景

**一句话**：让 LLM 把你的零散信息"编译"成持续增值的结构化知识库，而不是每次提问都从原始文档重新推导。

灵感来自 [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：

> Stop re-deriving, start compiling.

NoteAI 在原始资料和最终答案之间插入一个"编译层"——由 AI 主动维护的 Markdown 知识库。与 RAG 的本质区别：RAG 是无状态的检索，NoteAI 是有状态的编译。

**目标用户**：深度知识工作者——研究员、产品经理、工程师、写作者，任何需要长期积累和检索知识的人。

---

## 2. 现状评估

### 2.1 已实现（v1.0）

| 模块 | 能力 | 成熟度 |
|------|------|--------|
| 📥 采集 | 网页下载、PDF/DOCX/PPTX/TXT→MD 转换、AI 排版 | ★★★☆ |
| 🗂️ 整理 | 三层主题树、jieba 分词标签、笔记整合（3 种策略）、AI 主题分析 | ★★★☆ |
| 🔗 链接 | 双向链接发现（粗筛+AI 精判）、Canvas 力导向图、WIKI.md 索引 | ★★☆☆ |
| ✍️ 编辑 | Tiptap Markdown 编辑、marked.js 预览、AI 改写 | ★★★☆ |
| 💬 对话 | AI 助手面板、基于知识库的 RAG 问答（Milvus+FlagEmbedding） | ★★☆☆ |
| 📱 桌面 | Tauri 2 壳、Sidecar 进程架构、watchdog 文件监听 | ★★★☆ |

### 2.2 进行中（LangChain2 分支）

- 三层话题系统重构（topics_3tier）
- Abstract 综述文件夹方案四（独立于 Notes 的编译产物层）
- Chunker 改进（代码块/表格识别、重叠窗口）
- 主题节点综述状态标记和双击预览

### 2.3 结构性债务

- `ORGANIZED_FOLDER` / `ABSTRACT_FOLDER` 混用（已修复）
- JS API 函数缺失（如 `createTopicFolder`，已修复）
- 测试覆盖率低（仅 24 个测试用例）
- 无 CI/CD pipeline
- 前端代码部分仍在 index.html 内联，模块化未完成

---

## 3. Karpathy 理念对齐分析

Karpathy 描述的三层架构与 NoteAI 现状的映射：

| Karpathy 概念 | NoteAI 对应物 | 差距 |
|---------------|--------------|------|
| **Raw Sources**（不可变源） | `Raw/` 文件夹 | 缺少"源文档不可变"的语义保护 |
| **Wiki**（LLM 维护的编译层） | `Abstract/` + `Notes/` | 只完成了静态生成，缺少"源入→自动触达 15 个相关页面"的联动 |
| **Schema**（LLM 行为规范） | `prompts/` 目录 | 缺少 `SCHEMA.md` 类型的主配置文件，prompt 零散 |
| **Ingest**（源→摘要+索引+交叉引用） | 笔记整合 | 非流式，不自动触发交叉引用更新 |
| **Query**（搜索→合成→归档） | AI 助手 + RAG | 无法将好的回答归档为 wiki 页面 |
| **Lint**（矛盾/过时/孤儿检测） | ❌ 不存在 | 完全缺失 |
| **index.md**（每页一行摘要） | WIKI.md | 结构不同，WIKI.md 更像目录而非摘要索引 |
| **log.md**（可 grep 的操作日志） | activity_log | 结构不够标准化，不可 grep |

**结论：NoteAI 目前的"编译"是批量的、被动的，而不是增量的、主动的。v2.0 的核心命题是从"批处理知识工具"升级为"持续维护的知识编译器"。**

---

## 4. 竞品参考与主流方向（2025-2026）

| 产品 | 核心思路 | 可借鉴点 |
|------|---------|---------|
| **Notion AI** | 文档+AI 内嵌 | Q&A 直接引用页面，AI 自动填充属性 |
| **Obsidian + Copilot** | 本地 MD + 插件生态 | 社区驱动、Canvas、Dataview 查询 |
| **Mem** | AI 自动组织，无需手动分类 | AI 自动打标签、自动关联、AI Chat 引用记忆 |
| **Reflect** | 第二大脑，AI 辅助回忆 | 每日笔记 + AI 摘要 + 反向链接自动化 |
| **Fabric** | 开源 Pattern 库 | YouTube/Podcast→笔记的 Pipeline 模式 |
| **Granola** | AI 会议笔记 | 结构化会议模板+AI 增强 |
| **Cogram** | No-code LLM pipeline for docs | 可编程的知识处理管线 |
| **Rewind AI** | 全量记录+可搜索 | "记录一切"的愿景，但隐私成问题 |

**2025-2026 前沿方向**：

1. **Memory-based AI** — AI 拥有持久记忆，不是每次从零开始；Google Project Mariner、OpenAI Deep Research 都是这个方向
2. **Agentic Knowledge Base** — 知识库不只是被查询，而是能主动执行任务（"帮我整理本周 AI 论文"→自动搜索→下载→总结→归档）
3. **Graph RAG / Knowledge Graph RAG** — 从向量检索升级为图+向量混合检索，用实体关系提升检索精度
4. **Small-to-Big Retrieval** — 先检索句子级，再扩展到段落级，逐级精炼
5. **Multimodal Knowledge** — 图片、音频、视频作为一等知识载体，不只是文本附件
6. **Local-first + Privacy** — 数据本地化，AI 本地推理（Ollama/llama.cpp），不依赖云
7. **Collaborative Knowledge** — 团队共享知识库，AI 辅助知识对齐

---

## 5. 功能路线图

### P0 — 补齐 Karpathy 核心闭环（v2.0 必须）

#### 5.1 Schema 系统 — `SCHEMA.md`
**现状**：prompts/ 目录零散，没有统一的知识库结构规范。
**方案**：新增 `SCHEMA.md` 作为顶层配置，定义：
- Wiki 目录结构约定
- 页面模板（摘要页 / 概念页 / 实体页 / 对比页）
- 命名规范、Front Matter 字段
- LLM 维护行为规范（何时更新、更新范围、冲突解决）
- 与 Karpathy 的 CLAUDE.md 理念一致：人类和 LLM 共同演化这个文件

#### 5.2 Ingest 流式 Pipeline
**现状**：笔记整合是批处理，手动触发。
**方案**：新的 Ingest 事件驱动闭环：
```
新源进入 → LLM 阅读 → 生成摘要页 → 更新 index.md
    → 识别提及的实体/概念 → 更新相关页面 → 添加交叉引用
    → 追加 changelog 到 log.md
```
一个源可能触及 10-15 个页面，全自动。进度通过 sidecar event 推送到 UI。

#### 5.3 Lint 健康检查
**新增功能**，定期/手动触发以下检查：
- **矛盾检测**：不同页面对同一事实的陈述是否冲突
- **过时检测**：摘要页是否落后于源文件的更新
- **孤儿页面**：没有入链的页面（可删除候选）
- **缺失交叉引用**：页面 A 提到实体 B，但 A 没有链接到 B
- **数据缺口**：某个主题下文件数量异常少

输出 Lint 报告，用户确认后批量修复。

#### 5.4 Query → Archive 闭环
**现状**：AI 助手的对话是临时的，好的回答无法沉淀。
**方案**：在助手面板增加"保存到知识库"按钮，AI 将好的回答格式化为 wiki 页面，自动插入到合适的目录位置并更新索引。

#### 5.5 log.md 标准化
**现状**：`activity_log.py` 记录了操作但不标准。
**方案**：按 Karpathy 规范重构为 `log.md`：
```
## 2026-05-15

### Ingest `AI Agent 架构设计.md`
- 源: `Notes/AI Agent 架构设计.md`
- 摘要: `Abstract/AI Agent 架构/Agent 架构设计.md`
- 更新: `Abstract/AI Agent 架构/综述.md`、`WIKI.md`
- 交叉引用: `AI 产品经理之路/Agent 产品设计.md`

### Query "Agent 记忆系统怎么做" → 已归档为 `Abstract/Agent 记忆系统设计.md`
```
`grep "Ingest" log.md` 即可查看所有摄入记录。

---

### P1 — 知识深度与智能（v2.1）

#### 5.6 自动交叉引用引擎
**现状**：双向链接发现依赖手动触发。
**方案**：
- 文件保存时自动触发交叉引用分析（watchdog 事件驱动）
- 实体识别（提取人名、术语、工具名）→ 与已有页面匹配 → 自动添加链接
- 引用强度的可视化（强引用/弱引用/提及）

#### 5.7 Graph RAG 混合检索
**现状**：纯向量检索（Milvus + FastEmbed）。
**方案**：
- 构建知识图谱层（实体-关系-实体），与向量检索并行
- 查询时：向量检索获取语义相似块 + 图遍历获取关联实体
- 融合排序后喂给 LLM

#### 5.8 AI 原生编辑器
**现状**：AI 改写是选中→改写→预览→应用，体验割裂。
**方案**：
- `/` 命令菜单（slash commands）：`/summarize` `/展开` `/翻译` `/改写为要点` `/补充案例` `/反问`
- AI 内联补全（类似 Cursor Tab）：在上下文中自动建议下一句
- "Continue writing" 按钮，AI 分析上下文后续写

#### 5.9 知识版本化
**现状**：无版本管理，AI 更新可能覆盖重要人工编辑。
**方案**：
- 每个 wiki 页面维护变更历史（存储在 `.noteai/history/` 下）
- AI 编辑前后自动 diff
- 支持一键回退，标注"此段落为人工编辑，请勿覆盖"

#### 5.10 主动知识推送
**现状**：知识库是"拉取"模式（用户主动查询）。
**方案**：
- "本周回顾"邮件/通知：本周新增文件摘要、待处理主题、知识库变化概览
- "你知道吗"式发现：AI 发现两个看似无关的主题存在关联，主动推送给用户

---

### P2 — Agent 化与自动化（v2.2）

#### 5.11 Agent 型知识助手
**现状**：AI 助手是单轮/多轮对话，无自主行动能力。
**方案**：
- 助手可以执行操作：搜索文件、创建主题、生成综述、移动文件（类似 Claude Code 的工具调用模式）
- "帮我整理本周 AI 论文" → Agent 自动：搜索 → 下载 → 分类 → 摘要 → 归档 → 更新索引
- 支持定时任务（每天早上 9 点整理昨天的 RSS 订阅）

#### 5.12 多源自动采集
**新功能**：
- **RSS/Atom 订阅**：监控博客和新闻源，新文章自动下载入库
- **YouTube 转录**：订阅频道 → 新视频 → Whisper 转文字 → 摘要 → 存档
- **X/Twitter 书签**：收藏的推文 → 提取内容 → 存档
- **邮件集成**：转发邮件到指定地址 → 自动提取内容
- **浏览器扩展**：一键剪藏网页到 NoteAI

#### 5.13 Personal Memory（个人记忆系统）
**新功能**：Not AI 的通用记忆，而是关于"你"的记忆。
- AI 助手在对话中自动提取用户偏好、观点、决策理由
- 存储到用户 Profile（`profile.md`）
- 每次对话前加载，让 AI 越来越"懂你"
- 类似 ChatGPT Memory 但本地化、用户可控

#### 5.14 知识复习系统
**新功能**：
- **间隔重复（Spaced Repetition）**：AI 从知识库生成卡片，按 SM-2 算法推送复习
- **每日一问**：AI 根据知识库内容生成一个问题，回答后给出反馈
- **知识测验**：指定主题范围，AI 生成测验题

---

### P3 — 生态与协作（v2.3+）

#### 5.15 Local AI 支持
- 集成 Ollama / llama.cpp，无云端依赖
- 自动检测本地模型，提供"轻量本地 / 深度云端"双模式
- 本地模型处理分类、标签、小文件摘要；云端模型处理复杂综述、交叉引用检测

#### 5.16 移动端
- iOS/Android 阅读版：只读访问知识库，支持搜索和 AI 提问
- iCloud/Dropbox/Syncthing 同步
- 快速捕捉：拍照→OCR→存档、语音→转文字→存档

#### 5.17 发布与分享
- 一键发布选定页面为公开网页（GitHub Pages 风格）
- 导出为 PDF、ePub 整书
- 团队空间：共享知识库，多人协作编辑（基于 Git 合并）

#### 5.18 插件系统
- Prompt 模板市场（类比 Fabric Patterns）
- Ingest 插件接口（自定义采集源）
- Post-process 插件接口（自定义后处理）：翻译、校对、去重、格式转换

---

## 6. 架构建议

### 6.1 数据层重构

```
工作区/
├── Raw/              # 原始源文件，不可变（由系统保护）
├── Notes/            # 用户手动笔记 + 下载文章（可编辑）
├── Abstract/         # AI 编译产物（综述、摘要、概念页）— 方案四
├── .noteai/          # 系统元数据
│   ├── history/      # 页面变更历史
│   ├── embeddings/   # 向量索引（Milvus lite / ChromaDB）
│   ├── graph/        # 知识图谱（实体-关系）
│   ├── SCHEMA.md     # LLM 行为规范
│   ├── index.md      # 每页一行摘要，LLM 维护
│   ├── log.md        # 结构化操作日志，grep 友好
│   └── profile.md    # 用户记忆（偏好、观点、决策）
├── wiki/             # 手动维护的导航结构（WIKI.md）
└── media/            # 图片、视频、音频文件
```

### 6.2 Ingest Pipeline 架构

```
IngestManager (事件驱动)
├── SourceWatcher: watchdog 监听文件新增/修改
├── IngestPipeline:
│   ├── 1. Parse (格式识别 → MD)
│   ├── 2. Understand (LLM 阅读，提取要点)
│   ├── 3. Classify (主题匹配，置信度判断)
│   ├── 4. Summarize (生成 Abstract 页面)
│   ├── 5. CrossLink (实体识别 + 已有页面匹配)
│   ├── 6. Touch (更新所有相关页面的交叉引用)
│   └── 7. Index (更新 index.md 和 log.md)
├── LintScheduler: 定时/手动触发健康检查
└── ReviewQueue: 不确定项入队等待用户确认
```

### 6.3 前端模块化完成

```
webui/
├── index.html        # 主壳（< 500 行）
├── css/
│   ├── base.css
│   ├── editor.css
│   ├── tree.css
│   └── chat.css
├── js/
│   ├── api.js        # 统一 RPC 封装 （已有）
│   ├── state.js      # 集中状态管理 （待建）
│   ├── router.js     # 页面路由 （待建）
│   ├── modules/      # 按功能拆分
│   │   ├── editor.js
│   │   ├── tree.js
│   │   ├── chat.js
│   │   ├── graph.js
│   │   └── lint.js
│   └── lib/          # 第三方库
└── assets/           # 图标、字体
```

---

## 7. 优先级排序

| 优先级 | 功能 | 理由 |
|--------|------|------|
| **P0** | Schema 系统 | 没有 Schema，LLM 行为不可控 |
| **P0** | Ingest 流式 Pipeline | Karpathy 闭环的核心——"编译一次，持续增值" |
| **P0** | Lint 健康检查 | 知识库质量保证，自动化维护的核心 |
| **P0** | Query→Archive | 让对话产生积累，而不是随风消逝 |
| **P0** | log.md 标准化 | grep 友好，可审计，可回放 |
| **P1** | Graph RAG | 检索质量质变，图+向量双引擎 |
| **P1** | AI 原生编辑器 | 编辑体验从"工具"到"搭档" |
| **P1** | 知识版本化 | AI 编辑需要保险丝 |
| **P2** | Agent 型助手 | 从被动到主动的范式转换 |
| **P2** | 多源采集 | 知识库需要"活水" |
| **P2** | Personal Memory | 让 AI 越来越懂你 |
| **P3** | Local AI | 隐私和成本优势 |
| **P3** | 移动端 | 随时随地访问 |

---

## 8. 成功指标

- **编译覆盖率**：有 Abstract 综述的主题占比 > 80%
- **交叉引用密度**：平均每页面被引用次数 > 3
- **Lint 健康度**：知识库矛盾/过时/孤儿页面占比 < 5%
- **对话归档率**：AI 助手对话中"保存到知识库"操作的占比 > 20%
- **用户留存**：每周活跃天数 > 4 天
- **知识增长速度**：周均新增页面 > 10

---

*PRD 版本: v1.0 | 日期: 2026-05-15 | 基于 NoteAI LangChain2 分支现状*
