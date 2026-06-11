# NoteGen → NoteAI 功能合并建议 PRD

> 基于对 NoteGen（github.com/codexu/note-gen）的调研，提取可直接增强 NoteAI 的功能点。
> 目标：降低使用门槛、丰富碎片化记录入口、保留 NoteAI 核心编译能力。

---

## 一、NoteGen 是什么

- **定位**：跨平台 Markdown AI 笔记应用，主打"先记录、后整理、再写作"
- **技术栈**：Tauri v2 + Next.js + Tailwind CSS + TypeScript（纯前端，无 Python sidecar）
- **体积**：~20MB（比 NoteAI 小一个数量级）
- **核心模式**：三工作区分离 — Recording（记录）→ Notes（整理）→ AI Dialogue（对话）
- **存储**：原生 Markdown + GitHub/Gitee/WebDAV 同步

---

## 二、功能对比矩阵

| 功能 | NoteGen | NoteAI | 评估 |
|------|---------|--------|------|
| **截图 OCR 记录** | ✅ 核心功能（Tesseract.js） | ❌ 无 | **必合** — 碎片化记录最佳入口 |
| **剪贴板助手** | ✅ 自动识别剪贴板文字/图片 | ❌ 无 | **必合** — 降低记录摩擦 |
| **记录→整理→写作三工作区** | ✅ 明确分离 | ❌ 统一界面，入口重 | **必合** — 降低认知负担 |
| **标签系统** | ✅ 手动标签，简单 | ✅ AI 自动标签（jieba+TF-IDF） | NoteAI 已更强，无需合并 |
| **Markdown 编辑器** | ✅ WYSIWYG + 分屏预览 | ✅ Tiptap WYSIWYG + PDF/DOCX 预览 | NoteAI 已更强 |
| **AI 对话辅助** | ✅ 续写/润色/翻译/精简 | ✅ 小忆助手（Q&A + Agent 模式） | NoteAI 已更强 |
| **文件管理器** | ✅ 本地 + GitHub 仓库 | ✅ Notes/Raw/wiki 三级目录 | NoteAI 更结构化 |
| **版本管理** | ✅ 基于 Git 历史回溯 | ❌ 无 | **建议合** — 简单有效 |
| **图床/图片托管** | ✅ 粘贴自动上传图床 | ❌ 无 | **建议合** — 发文章刚需 |
| **HTML 转 Markdown** | ✅ 复制网页自动转换 | ❌ 无 | **建议合** — 采集刚需 |
| **全局搜索** | ✅ 标题+内容搜索 | ✅ 全文搜索 + 向量检索 | NoteAI 已更强 |
| **RAG / 知识库** | ✅ 内置简单 RAG | ✅ HyDE + 混合检索 + 重排序 | NoteAI 已更强 |
| **主题/外观** | ✅ 暗色主题 + 自定义 | ❌ 较朴素 | **可选合** — 提升体验 |
| **MCP 支持** | ✅ 有 | ✅ 有 | 持平 |
| **入库流水线** | ❌ 无 | ✅ 9 步可恢复流水线 | NoteAI 独有，保留 |
| **三级主题分类** | ❌ 二级目录 | ✅ L1>L2>L3 + AI 建议 | NoteAI 独有，保留 |
| **WIKI 综述** | ❌ 无 | ✅ 自动生成/级联更新 | NoteAI 独有，保留 |
| **知识图谱** | ❌ 无 | ✅ 力导向图可视化 | NoteAI 独有，保留 |
| **交叉引用** | ❌ 无 | ✅ 本地+AI 双向链接 | NoteAI 独有，保留 |
| **健康度指标** | ❌ 无 | ✅ 覆盖率/均链数/Lint | NoteAI 独有，保留 |

---

## 三、建议合并的功能（按优先级）

### 🔥 P0 — 立即做

#### 1. 截图 OCR 记录（Recording 入口）

**NoteGen 做法**：
- 快捷键截图 → Tesseract.js OCR → 生成一条"记录"
- 记录可附带标签、来源 URL
- 多条记录可一键"整理成笔记"

**合并到 NoteAI**：
- 在 NoteAI 侧边栏新增 **"快速记录"** 面板
- 支持：截图 OCR、粘贴图片 OCR、粘贴文字、拖拽文件
- 记录先进入 `Inbox/`（收件箱），不立即触发完整入库流水线
- 用户手动选择"整理入库"时才走 convert→compile→classify→index 流程

**价值**：把 NoteAI 从"先准备资料再打开"变成"随时能记"，降低 80% 使用门槛。

---

#### 2. 剪贴板助手

**NoteGen 做法**：
- 后台监听剪贴板，识别文字/图片/链接
- 弹出浮窗："检测到内容，是否记录？"
- 一键保存到记录列表

**合并到 NoteAI**：
- 作为可选后台服务（默认关闭，用户手动开启）
- 检测到剪贴板变化 → 识别类型 → 浮窗提示 → 用户确认后进入 Inbox
- 链接类型：自动 fetch 网页标题 + 摘要，存为待读

**价值**：看到好文章、好句子，复制即保存，不中断当前工作流。

---

#### 3. "记录→整理→写作"三模式切换

**NoteGen 做法**：
- 顶部 Tab 切换：Recording / Notes / AI Dialogue
- Recording：碎片记录列表，类似聊天
- Notes：文件管理器 + Markdown 编辑器
- AI Dialogue：对话界面，可引用记录和笔记

**合并到 NoteAI**：
- 当前 NoteAI 界面太重（编辑器+图谱+小忆+设置全挤在一起）
- 改为左侧导航栏三模式切换：
  - **📥 收件箱（Inbox）**：快速记录、待整理资料、统一收件箱（替代现在的"统一收件箱"概念）
  - **📝 工作区（Workspace）**：现有的 Notes/Raw/wiki 文件管理
  - **🤖 小忆（Xiao Yi）**：对话界面，但可以从 Inbox/Workspace 拖拽资料进来提问

**价值**：界面逻辑清晰，新用户 30 秒知道该点哪里。

---

### 🟡 P1 — 本月做

#### 4. 图床/图片托管

**NoteGen 做法**：
- 粘贴图片到编辑器 → 自动上传到配置的图床（GitHub/GitLab/S3）
- 返回 Markdown 图片链接

**合并到 NoteAI**：
- 在设置里新增"图床配置"：GitHub/GitLab/S3/阿里云 OSS
- 粘贴/拖拽图片时可选：本地存储（默认）或上传图床
- 上传后自动替换为图床链接

**价值**：写公众号/小红书/知乎时，图片外链直接可用，不用手动上传。

---

#### 5. HTML 转 Markdown（网页采集）

**NoteGen 做法**：
- 复制网页内容 → 粘贴到编辑器 → 自动清理为 Markdown
- 保留标题层级、链接、图片

**合并到 NoteAI**：
- 作为 Inbox 的输入方式之一：粘贴 URL → 自动 fetch → html2text → 进入 Inbox
- 或粘贴 HTML 内容 → 自动转换

**价值**：替代现在的"网页下载"功能，更轻量、更即时。

---

#### 6. Git 同步（替代实验性云同步）

**NoteGen 做法**：
- 绑定 GitHub/Gitee 私有仓库
- 自动 commit/push，历史可回溯
- 换设备 = clone 仓库

**合并到 NoteAI**：
- 在设置里新增"Git 同步"选项
- 初始化或绑定现有仓库
- 定时或手动同步：自动 commit（带消息摘要）
- 比 WebDAV/云盘更可靠，且有版本历史

**价值**：NoteAI 现在的云同步是实验性的，Git 同步更稳定、更开发者友好。

---

### 🟢 P2 — 季度内

#### 7. 暗色主题 / 外观定制

**NoteGen 做法**：
- 暗色/亮色切换
- Markdown、代码块外观可自定义

**合并到 NoteAI**：
- 先支持暗色主题（现在只有亮色）
- 后续支持编辑器字体、行高、配色方案

**价值**：长时间写作/阅读时，暗色主题更护眼。

---

## 四、不建议合并的功能

| 功能 | 原因 |
|------|------|
| NoteGen 的简单 RAG | NoteAI 的 HyDE + 混合检索 + 重排序已经更强 |
| NoteGen 的二级目录 | NoteAI 的三级主题 + AI 建议更结构化 |
| NoteGen 的基础 Markdown 编辑器 | NoteAI 的 Tiptap + PDF/DOCX 预览更强大 |
| NoteGen 的 AI 续写/润色 | NoteAI 的小忆助手（Agent 模式）更强大 |
| NoteGen 的全局搜索 | NoteAI 的全文+向量检索已覆盖 |

---

## 五、实施路线图

### Phase 1：Inbox 系统（2 周）

1. 新增 `Inbox/` 目录（与 `Notes/`、`Raw/`、`wiki/` 同级）
2. 新增"快速记录"面板：截图 OCR、粘贴、拖拽
3. 记录项数据结构：
   ```yaml
   id: uuid
   type: screenshot | text | image | link | file
   content: "..."
   source_url: "..."  # 可选
   tags: ["..."]
   created_at: "..."
   status: pending | processed | archived
   ```
4. 从 Inbox 一键"整理入库" → 触发现有入库流水线

### Phase 2：三模式界面（2 周）

1. 左侧导航栏改为三模式：Inbox / Workspace / Xiao Yi
2. Inbox 模式：记录列表 + 快速输入框
3. Workspace 模式：现有文件管理器 + 编辑器
4. Xiao Yi 模式：对话界面，支持从 Inbox/Workspace 拖拽资料

### Phase 3：增强功能（4 周）

1. 剪贴板助手（后台服务 + 浮窗）
2. 图床配置 + 自动上传
3. HTML 转 Markdown
4. Git 同步
5. 暗色主题

---

## 六、关键设计原则

1. **不破坏现有流水线**：Inbox 是入口，不是替代。资料从 Inbox 进入 Notes/Raw/wiki 时，仍然走完整的 convert→compile→classify→index→crossref→cascade→lint→sync。
2. **降低门槛，不降低深度**：新用户可以先只玩 Inbox（随手记），慢慢发现 Workspace 和 Xiao Yi 的强大。
3. **保持本地优先**：截图 OCR 用本地 Tesseract（或 macOS Vision API），不依赖云端。
4. **可选开启**：剪贴板助手、Git 同步、图床 —— 默认关闭，用户按需开启。

---

## 七、一句话总结

> **把 NoteGen 的"随手记"能力嫁接到 NoteAI 的"知识编译"引擎上 —— 让 NoteAI 既有便签本的轻量，又有图书馆的深度。**

---

*文档版本：v0.1*
*日期：2026-06-04*
*作者：AI 助手（基于用户指令生成）*
