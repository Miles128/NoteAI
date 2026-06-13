#!/usr/bin/env python3
"""Build semantic locale JSON from catalog and patch webui (HTML data-i18n + JS window.t)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "webui" / "locales"
HTML = ROOT / "webui" / "index.html"
JS_DIR = ROOT / "webui" / "js"

# (key, zh, en)
CATALOG: list[tuple[str, str, str]] = [
    # common
    ("common.cancel", "取消", "Cancel"),
    ("common.close", "关闭", "Close"),
    ("common.save", "保存", "Save"),
    ("common.saved", "已保存", "Saved"),
    ("common.loading", "加载中...", "Loading…"),
    ("common.loadingAlt", "加载中…", "Loading…"),
    ("common.error", "错误", "Error"),
    ("common.unknownError", "未知错误", "Unknown error"),
    ("common.retry", "重试", "Retry"),
    ("common.skip", "跳过", "Skip"),
    ("common.apply", "应用", "Apply"),
    ("common.resetDefault", "恢复默认", "Reset defaults"),
    ("common.collapse", "收起", "Collapse"),
    ("common.noWorkspace", "暂无工作区", "No workspace"),
    ("common.noData", "暂无数据", "No data"),
    ("common.items", "项", "items"),
    ("common.notesCount", "{count} 篇笔记", "{count} notes"),
    ("common.tagsCount", "{count} 个标签", "{count} tags"),
    ("common.linksCount", "{count} 个链接", "{count} links"),
    ("common.pendingCount", "{count} 项", "{count} items"),
    ("common.pendingRemaining", "{count} 项待处理", "{count} pending"),
    # titlebar
    ("titlebar.webDownload", "网页下载", "Download from web"),
    ("titlebar.importFiles", "导入文件", "Import files"),
    ("titlebar.openWorkspace", "打开工作区", "Open workspace"),
    ("titlebar.tree", "目录树", "File tree"),
    ("titlebar.tags", "标签", "Tags"),
    ("titlebar.links", "双向链接", "Bidirectional links"),
    ("titlebar.closePreview", "关闭预览", "Close preview"),
    ("titlebar.pending", "待处理", "Pending"),
    ("titlebar.aiAssistant", "AI 助手", "AI assistant"),
    ("titlebar.edit", "编辑", "Edit"),
    ("titlebar.relationGraph", "关系图谱", "Relation graph"),
    ("titlebar.search", "搜索 (Cmd+K)", "Search (Cmd+K)"),
    ("titlebar.settings", "设置", "Settings"),
    ("titlebar.expandSidebar", "展开侧边栏", "Expand sidebar"),
    # sidebar
    ("sidebar.collapse", "收起侧边栏", "Collapse sidebar"),
    ("sidebar.newTopic", "新建主题", "New topic"),
    ("sidebar.newNote", "新建笔记", "New note"),
    ("sidebar.tagPlaceholder", "输入标签名称...", "Enter tag name…"),
    ("sidebar.confirmCreateTag", "确认创建标签", "Confirm create tag"),
    ("sidebar.autoTagTitle", "自动匹配标签：扫描文件标题匹配已有标签", "Auto-match tags from file titles"),
    ("sidebar.addTagTitle", "新加标签：创建新的标签分类", "Create a new tag"),
    ("sidebar.discoverLinksTitle", "发现链接：AI 分析文章关联", "Discover links via AI"),
    # pending
    ("pending.title", "待处理", "Pending"),
    (
        "pending.hint",
        "主题/链接确认、综述失败、转换失败与健康检查问题，统一在此处理。",
        "Topic/link confirmations, survey failures, conversion errors, and health issues — all in one place.",
    ),
    ("pending.empty", "没有待处理的事项", "Nothing pending"),
    ("pending.allDone", "所有事项已处理完毕 ✓", "All done ✓"),
    ("pending.allDoneCelebration", "所有事项已处理完毕 🎉", "All done 🎉"),
    ("pending.healthCheck", "健康检查", "Health check"),
    ("pending.healthCheckRunning", "检查中…", "Checking…"),
    ("pending.retryAllSurveys", "全部重试综述", "Retry all surveys"),
    ("pending.retrying", "重试中…", "Retrying…"),
    ("pending.loadFailed", "加载失败: {error}", "Load failed: {error}"),
    ("pending.customTopicPlaceholder", "自定义主题...", "Custom topic…"),
    ("pending.selectTopic", "选择主题...", "Select topic…"),
    ("common.or", "或", "or"),
    # graph
    ("graph.stats.notes", "笔记", "Notes"),
    ("graph.stats.topics", "主题", "Topics"),
    ("graph.stats.survey", "综述", "Survey"),
    ("graph.stats.avgLinks", "均链", "Avg links"),
    ("graph.filter.topic", "主题", "Topics"),
    ("graph.filter.tag", "标签", "Tags"),
    ("graph.filter.all", "全部", "All"),
    ("graph.toggleFilenames", "显示/隐藏文件名", "Toggle filenames"),
    ("graph.zoomIn", "放大", "Zoom in"),
    ("graph.zoomOut", "缩小", "Zoom out"),
    ("graph.replay", "重放动画", "Replay animation"),
    ("graph.refresh", "刷新图谱", "Refresh graph"),
    ("graph.layoutSettings", "布局参数", "Layout settings"),
    ("graph.close", "关闭图谱", "Close graph"),
    ("graph.loading", "加载中...", "Loading…"),
    ("graph.empty", "暂无数据", "No data"),
    # preview / editor toolbar
    ("preview.selectFile", "选择文件以预览", "Select a file to preview"),
    ("editor.bold", "加粗", "Bold"),
    ("editor.italic", "斜体", "Italic"),
    ("editor.strike", "删除线", "Strikethrough"),
    ("editor.inlineCode", "行内代码", "Inline code"),
    ("editor.heading1", "标题 1", "Heading 1"),
    ("editor.heading2", "标题 2", "Heading 2"),
    ("editor.heading3", "标题 3", "Heading 3"),
    ("editor.bulletList", "无序列表", "Bullet list"),
    ("editor.orderedList", "有序列表", "Ordered list"),
    ("editor.taskList", "任务列表", "Task list"),
    ("editor.blockquote", "引用", "Quote"),
    ("editor.codeBlock", "代码块", "Code block"),
    ("editor.link", "链接", "Link"),
    ("editor.image", "图片", "Image"),
    ("editor.undo", "撤销", "Undo"),
    ("editor.redo", "重做", "Redo"),
    ("editor.llmRewrite", "LLM 改写：用中立客观风格重写文档", "LLM rewrite: neutral objective style"),
    # assistant
    ("assistant.panelTitle", "小忆助手", "XiaoYi Assistant"),
    ("assistant.mode.qa", "问答模式", "Q&A mode"),
    ("assistant.mode.agent", "助手模式", "Agent mode"),
    ("assistant.mode.badgeHint", "在设置 → 小忆助手中切换", "Switch in Settings → XiaoYi Assistant"),
    ("assistant.send", "发送", "Send"),
    ("assistant.name", "小忆", "XiaoYi"),
    ("assistant.system", "系统", "System"),
    (
        "assistant.welcome",
        "你好呀～我是小忆，你的知识小助手。想查笔记、理清思路，或有任何问题，直接告诉我就好～",
        "Hi! I'm XiaoYi, your knowledge assistant. Ask me about your notes or anything else.",
    ),
    ("assistant.requestFailed", "请求失败", "Request failed"),
    ("assistant.timeout", "响应超时，请检查 API 配置或稍后重试", "Request timed out. Check API settings or try again."),
    # settings nav
    ("settings.title", "设置", "Settings"),
    ("settings.nav.model", "模型", "Model"),
    ("settings.nav.ui", "界面", "Appearance"),
    ("settings.nav.assistant", "小忆助手", "XiaoYi Assistant"),
    ("settings.nav.activityLog", "操作记录", "Activity log"),
    ("settings.nav.schema", "Schema", "Schema"),
    ("settings.nav.about", "关于", "About"),
    ("settings.nav.cloudSync", "云盘同步", "Cloud sync"),
    ("settings.language", "语言", "Language"),
    ("settings.languageZh", "中文", "中文"),
    ("settings.languageEn", "English", "English"),
    ("settings.theme", "主题", "Theme"),
    ("settings.themeLight", "浅色", "Light"),
    ("settings.themeDark", "深色", "Dark"),
    ("settings.themePaper", "纸质", "Paper"),
    ("settings.themeSystem", "跟随系统", "System"),
    ("settings.fontSize", "字体大小", "Font size"),
    ("settings.fontSmall", "小", "Small"),
    ("settings.fontMedium", "中", "Medium"),
    ("settings.fontLarge", "大", "Large"),
    ("settings.fontSmallHint", "（默认）", "(default)"),
    ("settings.fontMediumHint", "（+2pt）", "(+2pt)"),
    ("settings.fontLargeHint", "（+4pt）", "(+4pt)"),
    ("settings.experimental", "实验功能", "Experimental"),
    ("settings.cloudSyncExperimental", "启用云盘同步（实验）", "Enable cloud sync (experimental)"),
    (
        "settings.cloudSyncExperimentalHint",
        "默认关闭。开启后设置侧栏显示「云盘同步」。",
        "Off by default. Shows Cloud sync in settings when enabled.",
    ),
    ("settings.saveConfig", "保存配置", "Save settings"),
    ("settings.llmApi", "LLM API", "LLM API"),
    ("settings.maxTokens", "最大 Tokens", "Max tokens"),
    ("settings.maxContext", "最大上下文", "Max context"),
    ("settings.thinkingChain", "思考链", "Thinking chain"),
    # search
    ("search.placeholder", "搜索笔记...", "Search notes…"),
    ("search.filterTopic", "主题过滤（含子串）", "Filter by topic"),
    ("search.filterTag", "标签过滤", "Filter by tag"),
    ("search.unavailable", "搜索不可用", "Search unavailable"),
    ("search.searching", "搜索中...", "Searching…"),
    ("search.failed", "搜索失败", "Search failed"),
    # download
    ("download.title", "下载", "Download"),
    ("download.tabWeb", "网页", "Web"),
    ("download.tabRss", "RSS", "RSS"),
    ("download.tabTranscript", "转录", "Transcript"),
    ("download.urlsPlaceholder", "每行一个 URL", "One URL per line"),
    ("download.rssPlaceholder", "RSS / Atom 订阅地址", "RSS / Atom feed URL"),
    ("download.rssCount", "条数", "Count"),
    ("download.rssFetch", "抓取原文", "Fetch full text"),
    ("download.importRss", "导入 RSS", "Import RSS"),
    ("download.transcriptTitle", "标题", "Title"),
    ("download.transcriptSource", "来源（可选）", "Source (optional)"),
    ("download.transcriptContent", "粘贴转录文本…", "Paste transcript…"),
    ("download.saveTranscript", "保存转录", "Save transcript"),
    ("download.includeImages", "包含图片的外部 URL 链接", "Include external image URLs"),
    ("download.start", "开始下载", "Start download"),
    # ingest
    ("ingest.label", "入库", "Ingest"),
    ("ingest.retry", "重试", "Retry"),
    ("ingest.cancel", "取消入库", "Cancel ingest"),
    ("ingest.retryTitle", "重新入库", "Retry ingest"),
    ("ingest.cancelTitle", "取消入库", "Cancel ingest"),
    # integrator (tab-1)
    ("integrator.cardTitle", "笔记整合", "Note integration"),
    (
        "integrator.statusLine",
        "从Notes文件夹读取markdown文件，整合输出到Abstract文件夹",
        "Read markdown from Notes/ and output to Abstract/",
    ),
    ("integrator.topicSettings", "主题设置", "Topic settings"),
    ("integrator.topicCount", "主题个数（留空则自动选择）", "Topic count (empty = auto)"),
    ("integrator.topicCountPlaceholder", "例如：5", "e.g. 5"),
    ("integrator.topicListHint", "点击提取主题，或手动输入（每行一个）", "Extract topics or enter one per line"),
    ("integrator.topicListPlaceholder", "主题1\n主题2\n主题3", "Topic 1\nTopic 2\nTopic 3"),
    ("integrator.extractTopics", "提取主题", "Extract topics"),
    ("integrator.start", "开始整合", "Start integration"),
    # links pending panel
    ("links.pendingTitle", "待确认链接", "Links to confirm"),
    ("links.confirmAll", "一键确认所有待确认链接", "Confirm all links"),
    ("links.pendingEmpty", "暂无待确认链接", "No links to confirm"),
    # quick create
    ("quickCreate.title", "快速新建", "Quick create"),
    ("quickCreate.tabNote", "新建笔记", "New note"),
    ("quickCreate.tabTopic", "新建主题", "New topic"),
    ("quickCreate.noteTitle", "标题", "Title"),
    ("quickCreate.noteTitlePlaceholder", "笔记标题", "Note title"),
    ("quickCreate.noteTopic", "主题（可选）", "Topic (optional)"),
    (
        "quickCreate.noteUncategorizedHint",
        "未选主题时保存到 Notes/_未分类/",
        "Saved to Notes/_uncategorized/ if no topic",
    ),
    ("quickCreate.createAndOpen", "创建并打开", "Create & open"),
    ("quickCreate.topicName", "主题名称", "Topic name"),
    ("quickCreate.topicNamePlaceholder", "例如：Agent 入门", "e.g. Agent basics"),
    ("quickCreate.topicParent", "上级主题（可选）", "Parent topic (optional)"),
    ("quickCreate.topicParentHint", "有上级时创建为「上级 > 名称」", 'With parent: "Parent > Name"'),
    ("quickCreate.createTopic", "创建主题", "Create topic"),
    ("quickCreate.uncategorized", "（无 / 未分类）", "(None / uncategorized)"),
    # schema wizard modal (titles only — body in schemaWizard.js)
    ("schemaWizard.modalTitle", "配置工作区 Schema", "Configure workspace schema"),
    ("schemaWizard.useDefault", "使用推荐默认", "Use recommended defaults"),
    ("schemaWizard.back", "上一步", "Back"),
    ("schemaWizard.next", "下一步", "Next"),
    ("schemaWizard.finish", "完成并保存", "Finish & save"),
    # project rules
    ("projectRules.title", "项目规则", "Project rules"),
    (
        "projectRules.desc",
        "定义此工作区的项目规则，AI 在回答问题时会参考这些规则。",
        "Rules for this workspace that AI uses when answering.",
    ),
    ("projectRules.save", "保存规则", "Save rules"),
    # app status
    ("app.loading", "正在加载...", "Loading…"),
    ("app.ready", "就绪", "Ready"),
    ("app.initDone", "初始化完成", "Ready"),
    ("app.backendExited", "Python 后端已退出", "Python backend exited"),
    ("app.backendRecovered", "Python 后端已恢复", "Python backend recovered"),
    ("app.backendStartFailed", "Python 后端启动失败", "Python backend failed to start"),
    ("app.llmRewriting", "LLM 正在改写文档…", "LLM rewriting document…"),
    (
        "app.startFailedAlert",
        "NoteAI 启动失败\n\n{message}\n\n请检查 Python 环境和依赖是否正确安装。",
        "NoteAI failed to start\n\n{message}\n\nCheck Python environment and dependencies.",
    ),
    # integrator hints
    ("integrator.extractTopicsHint", "提取主题：从网页内容中提取关键主题", "Extract topics from web content"),
    ("integrator.startHint", "开始整合：将内容整合到笔记中", "Integrate content into notes"),
    # graph stats hints
    ("graph.stats.surveyHint", "一级/二级主题中有综述的占比", "Survey coverage for L1/L2 topics"),
    ("graph.stats.avgLinksHint", "每篇笔记平均出链数", "Average outbound links per note"),
    ("graph.stats.lintHint", "Lint 问题总数", "Total Lint issues"),
    ("graph.stats.notesSuffix", " 笔记", " notes"),
    ("graph.stats.topicsSuffix", " 主题", " topics"),
    ("links.confirmAllBtn", "全部确认", "Confirm all"),
    # settings extended
    ("settings.modelLabel", "模型", "Model"),
    ("settings.testingConnection", "正在测试连接...", "Testing connection…"),
    ("settings.configSaved", "配置已保存", "Settings saved"),
    ("settings.saveFailed", "保存失败", "Save failed"),
    ("settings.logRefreshed", "日志已刷新", "Log refreshed"),
    ("settings.autoSaved", "配置已自动保存", "Settings auto-saved"),
    ("settings.autoSaveFailed", "配置保存失败: {message}", "Auto-save failed: {message}"),
    ("settings.profileSaved", "画像已保存", "Profile saved"),
    ("settings.schemaTitle", "工作区 Schema", "Workspace Schema"),
    (
        "settings.schemaHint",
        "定义 AI 可写范围、主题层级与冲突策略（schema.md）。",
        "Define AI write scope, topic hierarchy, and conflict policy (schema.md).",
    ),
    ("settings.schemaWizardBtn", "配置向导", "Setup wizard"),
    ("settings.schemaReloadBtn", "重新加载", "Reload"),
    ("settings.schemaEditorPlaceholder", "schema.md 内容…", "schema.md content…"),
    ("settings.schemaSaveBtn", "保存 Schema", "Save Schema"),
    ("settings.schemaSaved", "Schema 已保存", "Schema saved"),
    ("settings.maintenanceTitle", "资料维护", "Maintenance"),
    (
        "settings.maintenanceHint",
        "重新转换 Raw/ 下支持的 PDF、Word 等原件，生成 Markdown 笔记。",
        "Re-convert PDF, Word, etc. in Raw/ to Markdown notes.",
    ),
    ("settings.rawConvertBtn", "Raw 批量重转", "Batch re-convert Raw"),
    ("settings.assistantIntroTitle", "小忆助手", "XiaoYi Assistant"),
    (
        "settings.assistantIntro1",
        "小忆是你的知识库问答伙伴。默认<strong>问答模式</strong>下，她会检索笔记与综述来回答，并可<strong>搜索笔记、查看主题列表</strong>，无需开启助手模式。",
        "XiaoYi is your knowledge Q&A partner. In default <strong>Q&A mode</strong>, she searches notes and surveys, and can <strong>search notes and list topics</strong> without Agent mode.",
    ),
    (
        "settings.assistantIntro2",
        "开启<strong>助手模式</strong>后，小忆还可以在你的工作区里<strong>动手修改</strong>，例如：",
        "With <strong>Agent mode</strong>, XiaoYi can <strong>modify your workspace</strong>, for example:",
    ),
    (
        "settings.assistantCap1",
        "<strong>新建主题</strong> — 可建一级或二级主题；二级主题必须您明确指定所属一级，小忆不会自动猜测",
        "<strong>Create topics</strong> — L1 or L2; L2 requires you to specify the L1 parent",
    ),
    (
        "settings.assistantCap2",
        "<strong>移动笔记</strong> — 把某篇笔记归到指定主题下",
        "<strong>Move notes</strong> — assign a note to a topic",
    ),
    (
        "settings.assistantCap3",
        "<strong>更新综述</strong> — 为某个主题重新生成或刷新主题综述",
        "<strong>Update surveys</strong> — regenerate topic surveys",
    ),
    (
        "settings.assistantCap4",
        "<strong>整理知识库</strong> — 在需要时触发入库流水线（转换、分类、索引等）",
        "<strong>Organize KB</strong> — run ingest pipeline when needed",
    ),
    (
        "settings.assistantIntro3",
        "问答模式下也可随时说「有哪些主题」「搜一下 xxx 相关的笔记」。助手模式会逐步执行写操作并在对话里显示进度。LLM 接口请在「模型」分页配置。",
        "In Q&A mode, ask for topics or to search notes. Agent mode shows progress for write actions. Configure LLM under Model tab.",
    ),
    ("settings.agentModeTitle", "助手模式", "Agent mode"),
    ("settings.agentModeLabel", "开启助手模式", "Enable Agent mode"),
    (
        "settings.agentModeDesc",
        "关闭时仅问答与只读查询；开启后可新建主题、移动笔记、更新综述等",
        "Off: Q&A and read-only queries. On: create topics, move notes, update surveys, etc.",
    ),
    ("settings.profileTitle", "用户画像", "User profile"),
    (
        "settings.profileHint",
        "用 Markdown 描述你的背景与偏好，小忆会在问答和助手模式中参考这些内容调整回答风格。",
        "Describe your background and preferences in Markdown for personalized answers.",
    ),
    ("settings.profileSaveBtn", "保存画像", "Save profile"),
    (
        "settings.profilePlaceholder",
        "## 关于我\n\n- 职业：AI产品经理\n- 专业领域：NLP, RAG\n- 兴趣：大语言模型, AI Agent\n\n## 偏好\n\n- 回答风格：简洁\n- 回答深度：技术向",
        "## About me\n\n- Role: AI PM\n- Expertise: NLP, RAG\n- Interests: LLM, AI Agent\n\n## Preferences\n\n- Style: concise\n- Depth: technical",
    ),
    ("settings.indexTitle", "知识库索引", "Knowledge index"),
    (
        "settings.indexHint",
        "问答依赖向量索引。日常入库会自动维护；若检索结果明显不对，可手动全量重建（耗时较长，请在工作区空闲时操作）。",
        "Q&A uses vector index. Ingest maintains it daily; rebuild manually if search is wrong (slow).",
    ),
    ("settings.rebuildIndexBtn", "重建知识库索引", "Rebuild knowledge index"),
    ("settings.activityLogTitle", "操作记录", "Activity log"),
    (
        "settings.activityLogHint",
        "工作区内 AI 与入库操作，写入 wiki/log.md。健康检查会自动删除断链、更新过时综述。",
        "AI and ingest actions logged to wiki/log.md. Health check fixes broken links and stale surveys.",
    ),
    ("settings.activityLogLoading", "加载中…", "Loading…"),
    (
        "settings.aboutDesc",
        "NoteAI 是一款智能知识管理工具，帮助用户高效组织和管理 Markdown 笔记。",
        "NoteAI helps you organize and manage Markdown notes with AI.",
    ),
    ("settings.aboutFeatures", "功能：", "Features:"),
    ("settings.aboutFeature1", "多层主题树知识图谱", "Multi-level topic tree & graph"),
    ("settings.aboutFeature2", "AI 辅助写作与内容整合", "AI-assisted writing & integration"),
    ("settings.aboutFeature3", "网页内容下载与分析", "Web download & analysis"),
    ("settings.aboutFeature4", "标签与双向链接管理", "Tags & bidirectional links"),
    ("settings.aboutTech", "技术栈：", "Tech stack:"),
    ("settings.aboutTechLine", "Tauri v2 + Python Sidecar + D3.js", "Tauri v2 + Python Sidecar + D3.js"),
    (
        "settings.aboutTechDesc",
        "基于 Rust 构建桌面端，Python 提供 AI 能力，D3.js 渲染知识图谱。",
        "Rust desktop shell, Python AI sidecar, D3.js graph.",
    ),
    # pending item types
    ("pending.typeTopic", "主题确认", "Topic confirmation"),
    ("pending.typeLink", "链接确认", "Link confirmation"),
    ("pending.confirmLink", "确认链接", "Confirm link"),
    ("pending.rejectLink", "拒绝", "Reject"),
    ("pending.operationFailed", "操作失败", "Operation failed"),
    ("pending.logEmpty", "暂无操作记录", "No activity yet"),
    ("pending.todoBadge", "待办事项 ({count})", "Pending items ({count})"),
    ("pending.todoBadgeEmpty", "待办事项", "Pending items"),
    ("graph.stats.surveyLabel", "综述 ", "Survey "),
    ("graph.stats.avgLinksLabel", "均链 ", "Avg "),
    # confirm dialog
    ("confirm.cancel", "取消", "Cancel"),
    ("confirm.ok", "确认", "Confirm"),
    # schema wizard (modal in index.html)
    ("schemaWizard.stepPurpose", "这个工作区主要做什么？", "What is this workspace for?"),
    (
        "schemaWizard.stepPurposeHint",
        "决定目录说明与整理语气的默认表述。",
        "Sets default tone for folder descriptions.",
    ),
    ("schemaWizard.purposePersonal", "个人知识库 — 长期积累、学习笔记", "Personal KB — long-term learning notes"),
    ("schemaWizard.purposeProject", "项目文档库 — 围绕单一产品/课题", "Project docs — single product or topic"),
    ("schemaWizard.purposeResearch", "研究资料库 — 论文、报告、摘录为主", "Research archive — papers and excerpts"),
    ("schemaWizard.stepDomains", "关注哪些知识领域？", "Which knowledge domains?"),
    (
        "schemaWizard.stepDomainsHint",
        "可多选，将生成一级主题示例（可在 project_rules 中再改）。",
        "Multi-select; generates L1 topic examples (editable in project_rules).",
    ),
    ("schemaWizard.domainRag", "RAG 与检索", "RAG & retrieval"),
    ("schemaWizard.domainProduct", "AI 产品", "AI product"),
    ("schemaWizard.domainLlm", "大模型应用", "LLM applications"),
    ("schemaWizard.domainTools", "工具与效率", "Tools & productivity"),
    ("schemaWizard.domainCareer", "职业成长", "Career growth"),
    (
        "schemaWizard.customDomainsPlaceholder",
        "其他一级主题，逗号分隔，如：产品设计, 开源社区",
        "Other L1 topics, comma-separated",
    ),
    ("schemaWizard.stepDepth", "主题层级与语言", "Topic depth & language"),
    ("schemaWizard.stepDepthHint", "对应 Notes/ 文件夹深度与命名习惯。", "Maps to Notes/ folder depth and naming."),
    ("schemaWizard.depth2", "以两级为主（一级 > 二级）", "Mostly 2 levels (L1 > L2)"),
    ("schemaWizard.depth3", "标准三级（一级 > 二级 > 三级）", "Standard 3 levels (L1 > L2 > L3)"),
    ("schemaWizard.langZh", "中文优先（文件名、标签、主题）", "Chinese first (names, tags, topics)"),
    ("schemaWizard.langMixed", "中英混合（专有名词保留英文）", "Mixed CN/EN (keep proper nouns in English)"),
    ("schemaWizard.stepHabits", "整理习惯", "Organization habits"),
    (
        "schemaWizard.stepHabitsHint",
        "写入 schema.md，约束 AI 自动整理行为。",
        "Written to schema.md to constrain AI organization.",
    ),
    ("schemaWizard.habitFolderTruth", "文件夹路径是主题唯一依据", "Folder path is the sole topic source"),
    ("schemaWizard.habitPending", "不确定分类 → 待办，不硬塞", "Uncertain → pending, never force-fit"),
    ("schemaWizard.habitSurveyOnly", "级联只更新综述，不改笔记正文", "Cascade updates surveys only, not note bodies"),
    ("schemaWizard.habitAutoConvert", "自动转换 PDF/DOCX 等", "Auto-convert PDF/DOCX etc."),
    ("schemaWizard.habitTagsCn", "标签 2～5 个，中文优先", "2–5 tags, Chinese preferred"),
    ("schemaWizard.stepConfirm", "确认生成的 schema.md", "Confirm generated schema.md"),
    (
        "schemaWizard.stepConfirmHint",
        "将保存到工作区根目录，并同步生成 project_rules.md。",
        "Saved to workspace root; syncs project_rules.md.",
    ),
    (
        "projectRules.placeholder",
        "## 项目规则\n\n- 本项目是关于 XXX 的知识库\n- 所有笔记使用中文\n- 代码示例使用 Python\n- 优先使用简洁的技术文档风格",
        "## Project rules\n\n- This KB is about XXX\n- Notes in Chinese\n- Code examples in Python\n- Concise technical style",
    ),
    # schema wizard status
    ("schemaWizard.saved", "工作区 Schema 已保存", "Workspace schema saved"),
    ("schemaWizard.saveFailed", "保存 Schema 失败: {message}", "Failed to save schema: {message}"),
    ("schemaWizard.selectDomain", "请至少选择一个知识领域", "Select at least one domain"),
    ("schemaWizard.saveUnavailable", "saveSchema 不可用", "saveSchema unavailable"),
    # quick create messages
    ("quickCreate.enterTopicName", "请输入主题名称", "Enter a topic name"),
    ("quickCreate.enterNoteTitle", "请输入笔记标题", "Enter a note title"),
    ("quickCreate.topicCreated", "主题已创建", "Topic created"),
    ("quickCreate.noteCreated", "笔记已创建", "Note created"),
    ("quickCreate.createFailed", "创建失败: {message}", "Create failed: {message}"),
    # time
    ("common.timeJustNow", "刚刚", "Just now"),
    ("common.timeMinutesAgo", "{count} 分钟前", "{count} min ago"),
    ("common.timeHoursAgo", "{count} 小时前", "{count} hr ago"),
    ("common.timeDaysAgo", "{count} 天前", "{count} days ago"),
    ("common.timeMonthDay", "{month} 月 {day} 日", "{month}/{day}"),
    ("common.confirmDelete", "确认删除", "Confirm delete"),
    ("common.confirmDeleteTopic", "确认删除主题", "Confirm delete topic"),
    ("common.file", "文件", "File"),
    ("common.backendError", "后端错误", "Backend error"),
    ("common.errorOccurred", "发生错误", "An error occurred"),
    # tree
    ("tree.revealInFinder", "在访达中显示", "Reveal in Finder"),
    ("tree.openInNewWindow", "在新窗口打开", "Open in new window"),
    ("tree.deleteTopic", "删除主题", "Delete topic"),
    ("tree.deleteFolder", "删除文件夹", "Delete folder"),
    ("tree.delete", "删除", "Delete"),
    (
        "tree.deleteTopicConfirm",
        "删除主题「{name}」？（文件将移至 Notes 根目录）",
        'Delete topic "{name}"? (Files move to Notes root)',
    ),
    ("tree.deleteConfirm", "删除「{name}」？", 'Delete "{name}"?'),
    (
        "tree.enterTopicName",
        "请输入新主题名称：\n\n将创建对应的主题文件夹，并自动匹配相关文件。",
        "Enter new topic name:\n\nCreates folder and auto-matches files.",
    ),
    ("tree.deleteTopicFailed", "删除主题失败: ", "Delete topic failed: "),
    ("tree.deleteTopicError", "删除主题出错: ", "Delete topic error: "),
    ("tree.createTopicFailed", "创建主题失败: ", "Create topic failed: "),
    ("tree.createTopicError", "创建主题出错: ", "Create topic error: "),
    ("tree.deleteFailed", "删除失败: ", "Delete failed: "),
    ("tree.deleteError", "删除出错: ", "Delete error: "),
    ("tree.confirmDeleteItem", '确定要删除 "{name}" 吗？', 'Delete "{name}"?'),
    ("tree.workspaceNotSet", "工作区未设置", "Workspace not set"),
    ("tree.workspaceEmpty", "工作区为空", "Workspace is empty"),
    ("tree.loadFailed", "暂时无法加载文件树", "Could not load file tree"),
    ("tree.loadTimeout", "加载超时", "Load timeout"),
    ("tree.invalidFormat", "文件树返回格式错误: {detail}", "Invalid tree response: {detail}"),
    # topic sidebar & actions
    ("topic.loading", "加载中…", "Loading…"),
    ("topic.invalidResponse", "无效响应", "Invalid response"),
    ("topic.noTopics", "暂无主题", "No topics yet"),
    ("topic.rename", "重命名", "Rename"),
    ("topic.addSubTopic", "添加子主题", "Add subtopic"),
    ("topic.confirmTopicFailed", "确认主题失败: ", "Confirm topic failed: "),
    ("topic.moveFailed", "移动失败: ", "Move failed: "),
    ("topic.createSubTopicFailed", "创建子主题失败: ", "Create subtopic failed: "),
    ("topic.createSubTopicError", "创建子主题出错", "Create subtopic error"),
    ("topic.deleteTopicFailed", "删除主题失败: ", "Delete topic failed: "),
    ("topic.deleteTopicError", "删除主题出错", "Delete topic error"),
    ("topic.autoAssignFailed", "自动分配主题失败: ", "Auto-assign failed: "),
    ("topic.selectOrEnterTopic", "请选择或输入一个主题", "Select or enter a topic"),
    ("topic.applyFailed", "应用失败: ", "Apply failed: "),
    ("topic.applyError", "应用出错: ", "Apply error: "),
    ("topic.allSuggestionsProcessed", "所有建议已处理", "All suggestions processed"),
    ("topic.aiScanning", "AI 正在扫描全量文件分析主题…", "AI scanning files for topics…"),
    ("topic.connectingLlm", "正在连接大模型…", "Connecting to LLM…"),
    ("topic.suggestionsCount", "{count} 条建议", "{count} suggestions"),
    ("topic.aiAnalysisDone", "AI 分析完成，共 {count} 条建议", "AI analysis done: {count} suggestions"),
    ("topic.topicsOk", "主题分配合理", "Topics look good"),
    ("topic.aiAnalysisAllOk", "AI 分析完成：所有文件主题分配合理", "AI analysis done: all topics look good"),
    ("topic.analysisFailed", "分析失败", "Analysis failed"),
    ("topic.aiNoResult", "AI 分析未返回结果", "AI returned no result"),
    ("topic.analysisError", "分析出错", "Analysis error"),
    ("topic.aiAnalysisError", "AI 分析出错: ", "AI analysis error: "),
    ("topic.noTopicsYet", "当前没有主题，请先创建主题", "No topics yet — create one first"),
    (
        "topic.enterSubTopicName",
        "请输入子主题名称：\n\n将添加到「{parent}」下",
        'Enter subtopic name:\n\nAdds under "{parent}"',
    ),
    (
        "topic.confirmDeleteTopic",
        "确定要删除主题「{name}」吗？\n\n该主题下的文件将从 WIKI.md 中移除，文件的 topic 标签也会被删除，之后会重新尝试自动匹配主题。",
        'Delete topic "{name}"?\n\nRemoves files from WIKI.md and clears topic tags; auto-match will retry.',
    ),
    (
        "topic.syncDone",
        "同步完成：移动 {moved}，新增 {added}，移除 {removed}，删除空主题 {deleted}",
        "Sync done: moved {moved}, added {added}, removed {removed}, deleted {deleted} empty topics",
    ),
    (
        "topic.scanDone",
        "扫描完成：共 {total} 个文件，自动分配 {assigned} 个，待确认 {pending} 个，跳过 {skipped} 个",
        "Scan done: {total} files, {assigned} assigned, {pending} pending, {skipped} skipped",
    ),
    ("topic.aiWritingSurvey", "AI 正在撰写 {topic} 综述…", "AI writing survey for {topic}…"),
    ("topic.writingSurvey", "正在撰写综述…", "Writing survey…"),
    ("topic.surveyDone", "综述撰写完成，已保存为 {path}", "Survey saved to {path}"),
    ("topic.surveySaved", "综述已保存", "Survey saved"),
    ("topic.writeFailed", "撰写失败: ", "Write failed: "),
    ("topic.surveyWriteFailed", "综述撰写失败", "Survey write failed"),
    ("topic.writeFailedShort", "撰写失败", "Write failed"),
    ("topic.writeError", "撰写出错: ", "Write error: "),
    ("topic.surveyWriteError", "综述撰写出错", "Survey write error"),
    ("topic.createTopicFailed", "创建主题失败", "Create topic failed"),
    (
        "topic.enterSurveyTopic",
        "请输入要撰写综述的主题：\n\n现有主题：{topics}",
        "Topic for survey:\n\nExisting: {topics}",
    ),
    (
        "topic.topicCreatedScan",
        "主题「{name}」创建成功。扫描完成：自动分配 {assigned} 个，待确认 {pending} 个",
        'Topic "{name}" created. Scan: {assigned} assigned, {pending} pending',
    ),
    ("topic.changeName", "更改名称", "Rename"),
    ("topic.aiSuggestionTitle", "AI 主题建议", "AI topic suggestions"),
    ("topic.typeNewTopic", "新建主题", "New topic"),
    ("topic.typeAssignTopic", "归档文件", "Assign file"),
    ("topic.typeMergeTopic", "合并主题", "Merge topics"),
    ("topic.typeChangeTopic", "变更主题", "Change topic"),
    ("topic.existingTopic", "已有主题", "Existing topic"),
    ("topic.newTopicTag", "全新主题", "New topic"),
    ("topic.labelFile", "文件", "File"),
    ("topic.labelOriginalTopic", "原始主题", "Original topic"),
    ("topic.noCurrentTopic", "当前没有主题", "No current topic"),
    ("topic.labelSuggestedTopic", "建议主题", "Suggested topic"),
    ("topic.selectExistingTopic", "-- 选择已有主题 --", "-- Select existing topic --"),
    ("topic.createTopicBody", "创建主题 {topic}{files}", "Create topic {topic}{files}"),
    ("topic.includesFiles", "，包含 {files}", ", includes {files}"),
    ("topic.assignFileBody", "将 {file} 归入主题 {topic}", "Assign {file} to {topic}"),
    ("topic.mergeTopicBody", "将 {source} 合并到 {target}", "Merge {source} into {target}"),
    ("topic.acceptSuggestion", "采纳", "Accept"),
    ("topic.rejectSuggestion", "忽略", "Reject"),
    ("topic.customTopicPlaceholder", "输入自定义主题", "Enter custom topic"),
    ("topic.suggestionTopicPlaceholder", "输入主题名称", "Enter topic name"),
    ("common.ok", "确定", "OK"),
    ("download.unnamed", "未命名", "Untitled"),
    ("integrator.scanningFiles", "正在扫描文件…", "Scanning files…"),
    ("graph.paramGroup.l1Global", "一级与全局", "L1 & global"),
    ("graph.paramGroup.l2Layout", "二级布局", "L2 layout"),
    ("graph.paramGroup.l3Layout", "三级布局", "L3 layout"),
    ("graph.paramGroup.noteScatter", "笔记散布", "Note scatter"),
    ("graph.paramGroup.l2RingFormula", "二级环半径公式", "L2 ring formula"),
    ("graph.paramGroup.l3RingFormula", "三级环半径公式", "L3 ring formula"),
    ("graph.paramGroup.simulation", "力学模拟", "Force simulation"),
    ("graph.paramGroup.nodeDisplay", "节点显示", "Node display"),
    ("graph.paramGroup.view", "视图", "Viewport"),
    ("graph.paramGroup.replay", "重播动画", "Replay animation"),
    ("graph.legend.notes", "笔记", "Notes"),
    ("graph.legend.tags", "标签", "Tags"),
    ("graph.legend.l2", "二级", "L2"),
    ("graph.legend.l3", "三级", "L3"),
    ("graph.param.l1PackRatio", "一级主题间距（× 画布短边）", "L1 topic spacing (× canvas short side)"),
    ("graph.param.orphanRadiusRatio", "孤立节点环半径（× 画布短边）", "Orphan ring radius (× canvas short side)"),
    ("graph.param.l1NoteMaxRingRatio", "一级笔记盘 / 二级环 最大比例", "L1 note disk / L2 ring max ratio"),
    ("graph.param.l2AnnulusGap", "一级笔记盘与二级环带间距 (px)", "L1 note disk to L2 ring gap (px)"),
    ("graph.param.l2InnerFallbackRatio", "无一级笔记时二级环带内径比例", "L2 ring inner radius when no L1 notes"),
    ("graph.param.l2OuterRingRatio", "二级环带外径 / 环半径", "L2 ring outer / ring radius"),
    ("graph.param.annulusMinSpan", "环带最小宽度 (px)", "Annulus min width (px)"),
    ("graph.param.annulusSingleTopicRatio", "单个主题在环带上的半径比例", "Single topic radius on annulus"),
    ("graph.param.annulusAngleOffset", "环带起始角偏移 (rad)", "Annulus start angle offset (rad)"),
    ("graph.param.l3InnerRatio", "三级主题环带内径比例", "L3 topic ring inner ratio"),
    ("graph.param.l3InnerMinGap", "三级环带内径最小间隙 (px)", "L3 ring inner min gap (px)"),
    ("graph.param.noteDiskMin", "笔记盘半径下限 (px)", "Note disk radius min (px)"),
    ("graph.param.noteDiskMax", "笔记盘半径上限 (px)", "Note disk radius max (px)"),
    ("graph.param.noteDiskBase", "笔记盘半径基数 (px)", "Note disk radius base (px)"),
    ("graph.param.noteDiskSqrtCoef", "笔记盘半径 √n 系数", "Note disk radius √n coefficient"),
    ("graph.param.noteSingleRadiusRatio", "单篇笔记半径比例", "Single note radius ratio"),
    ("graph.param.l2RingMin", "二级环半径下限 (px)", "L2 ring radius min (px)"),
    ("graph.param.l2RingMax", "二级环半径上限 (px)", "L2 ring radius max (px)"),
    ("graph.param.l2RingBase", "二级环半径基数 (px)", "L2 ring radius base (px)"),
    ("graph.param.l2RingSqrtL2", "二级环 √(二级数) 系数", "L2 ring √(L2 count) coef"),
    ("graph.param.l2RingSqrtNotes", "二级环 √(笔记数) 系数", "L2 ring √(note count) coef"),
    ("graph.param.l3RingMin", "三级环半径下限 (px)", "L3 ring radius min (px)"),
    ("graph.param.l3RingMax", "三级环半径上限 (px)", "L3 ring radius max (px)"),
    ("graph.param.l3RingBase", "三级环半径基数 (px)", "L3 ring radius base (px)"),
    ("graph.param.l3RingSqrtL3", "三级环 √n 系数", "L3 ring √n coefficient"),
    ("graph.param.topicCollidePad", "主题碰撞边距 (px)", "Topic collide padding (px)"),
    ("graph.param.fileCollidePad", "笔记碰撞边距 (px)", "Note collide padding (px)"),
    ("graph.param.chargeL1", "一级主题斥力", "L1 topic repulsion"),
    ("graph.param.chargeTopic", "二/三级主题斥力", "L2/L3 topic repulsion"),
    ("graph.param.chargeFile", "笔记斥力", "Note repulsion"),
    ("graph.param.targetStrengthTopic", "主题回拉强度 (0–1)", "Topic target strength (0–1)"),
    ("graph.param.targetStrengthFile", "笔记回拉强度 (0–1)", "Note target strength (0–1)"),
    ("graph.param.clusterRepelDist", "簇间互斥生效距离 (px)", "Cluster repel distance (px)"),
    ("graph.param.clusterRepelForce", "簇间互斥力度", "Cluster repel force"),
    ("graph.param.collideIterations", "碰撞迭代次数", "Collide iterations"),
    ("graph.param.simAlpha", "模拟初始 alpha", "Simulation initial alpha"),
    ("graph.param.simAlphaDecay", "模拟 alpha 衰减", "Simulation alpha decay"),
    ("graph.param.simVelocityDecay", "速度衰减", "Velocity decay"),
    ("graph.param.radiusL1", "一级主题圆半径 (px)", "L1 topic circle radius (px)"),
    ("graph.param.radiusOther", "其他节点圆半径 (px)", "Other node circle radius (px)"),
    ("graph.param.fitPad", "缩放适应边距 (px)", "Fit padding (px)"),
    ("graph.param.fitMaxScale", "最大缩放比例", "Max zoom scale"),
    ("graph.param.clampSideRatio", "拖拽边界留白（× 宽）", "Drag bounds margin (× width)"),
    ("graph.param.boundsMargin", "包围盒边距 (px)", "Bounds margin (px)"),
    ("graph.param.replayRevealMinMs", "逐层显示最短间隔 (ms)", "Reveal min interval (ms)"),
    ("graph.param.replayRevealMaxMs", "逐层显示最长间隔 (ms)", "Reveal max interval (ms)"),
    ("graph.param.replayRevealBudgetMs", "重播总时长预算 (ms)", "Replay total budget (ms)"),
    ("topic.pendingHeader", "待确认主题", "Topics to confirm"),
    # assistant
    ("assistant.userAvatar", "机器狗", "Robodog"),
    ("assistant.requestFailedMsg", "请求失败: {message}", "Request failed: {message}"),
    ("assistant.indexBuildDone", "知识库索引构建完成，共 {count} 个片段", "Index built: {count} chunks"),
    ("assistant.indexBuildFailed", "索引构建失败: {message}", "Index build failed: {message}"),
    (
        "assistant.indexBuilding",
        "正在构建知识库索引…（手动全量重建，日常入库不会重复跑）",
        "Building knowledge index… (manual full rebuild)",
    ),
    ("assistant.indexRequestFailed", "索引构建请求失败: {message}", "Index build request failed: {message}"),
    ("assistant.insightHint", "小忆觉得这段回答有洞见，可以单独存成笔记", "Save this insightful reply as a note?"),
    ("assistant.saveAsNote", "保存为笔记", "Save as note"),
    ("assistant.saving", "保存中", "Saving…"),
    ("assistant.savedToNotes", "已保存到 Notes/小忆对话", "Saved to Notes/XiaoYi chats"),
    ("assistant.saveFailed", "保存失败: {message}", "Save failed: {message}"),
    # app
    ("app.importing", "正在导入 {count} 个文件", "Importing {count} files…"),
    ("app.importProgress", "导入中", "Importing…"),
    ("app.importDone", "导入完成：{imported} 个文件", "Import done: {imported} files"),
    (
        "app.importDoneWithFailed",
        "导入完成：{imported} 个文件，{failed} 个失败",
        "Import done: {imported} files, {failed} failed",
    ),
    ("app.importFailed", "导入失败: {message}", "Import failed: {message}"),
    ("app.importFailedGeneric", "导入失败", "Import failed"),
    ("app.rewritingChars", "LLM 正在改写 {count} 字", "LLM rewriting… {count} chars"),
    ("app.rewriteFailed", "改写失败: {message}", "Rewrite failed: {message}"),
    ("app.rewriteFailedShort", "改写失败", "Rewrite failed"),
    ("app.rewriteDiffTitle", "改写对比", "Rewrite diff"),
    ("app.rewriteAccept", "✓ 采用新版本", "✓ Accept new version"),
    ("app.rewriteKeepOriginal", "✕ 保留原版本", "✕ Keep original"),
    ("app.rewriteOriginal", "原文", "Original"),
    ("app.rewriteResult", "改写后", "Rewritten"),
    ("app.rewriteDoneConfirm", "改写完成，请确认是否采用新版本", "Rewrite done — accept new version?"),
    ("app.saving", "正在保存", "Saving…"),
    ("app.saveFailed", "保存失败: {message}", "Save failed: {message}"),
    ("app.saveError", "保存出错: {message}", "Save error: {message}"),
    ("app.rewriteCancelled", "已放弃改写", "Rewrite discarded"),
    ("app.selectFileFirst", "请先选择一个文件", "Select a file first"),
    (
        "app.rewriteConfirm",
        "确定要用 LLM 改写此文档吗？\n改写后将用中立客观的笔记风格重写，改写完成后可对比确认。",
        "Rewrite this document with LLM?\nUses neutral note style; you can compare before accepting.",
    ),
    ("app.rewritingDoc", "正在改写文档", "Rewriting document…"),
    ("app.rewriteError", "改写出错: {message}", "Rewrite error: {message}"),
    ("app.autoAssignedTo", "已自动分配到「{topic}」", 'Auto-assigned to "{topic}"'),
    ("app.autoAssignedTopic", "已自动分配主题", "Topic auto-assigned"),
    ("app.errorPrefix", "错误: ", "Error: "),
    ("app.autoConvertDone", "自动转换完成 {done}/{total} 个文件", "Auto-convert done: {done}/{total} files"),
    ("app.indexBuilding", "索引构建中", "Building index…"),
    ("app.checkingSurveys", "检查综述中", "Checking surveys…"),
    ("app.ragIndexFailed", "RAG 索引构建失败", "RAG index build failed"),
    ("app.updatingSurvey", "正在更新综述 {topic}", "Updating survey: {topic}"),
    ("app.surveyNewTopic", "新主题已创建并生成综述", "New topic created with survey"),
    ("app.surveyUpdated", "综述已更新", "Survey updated"),
    ("app.cascadeFailed", "级联更新失败 {topic}", "Cascade update failed: {topic}"),
    # cloud sync
    ("cloudSync.connected", "已连接", "Connected"),
    ("cloudSync.disconnected", "未连接", "Not connected"),
    ("cloudSync.authLogin", "授权登录", "Authorize"),
    ("cloudSync.push", "↑ 推送", "↑ Push"),
    ("cloudSync.pull", "↓ 拉取", "↓ Pull"),
    ("cloudSync.disconnect", "断开", "Disconnect"),
    ("cloudSync.neverSynced", "尚未同步", "Never synced"),
    ("cloudSync.lastSync", "上次同步：{time}", "Last sync: {time}"),
    ("cloudSync.authing", "授权中...", "Authorizing…"),
    ("cloudSync.authSuccess", "授权成功", "Authorized"),
    ("cloudSync.authFailed", "授权失败", "Authorization failed"),
    ("cloudSync.authFailedMsg", "授权失败：{message}", "Authorization failed: {message}"),
    ("cloudSync.pushing", "推送中...", "Pushing…"),
    ("cloudSync.pushingStatus", "正在推送...", "Pushing…"),
    ("cloudSync.pushDone", "推送完成", "Push complete"),
    ("cloudSync.pushFailed", "推送失败", "Push failed"),
    ("cloudSync.pushFailedMsg", "推送失败：{message}", "Push failed: {message}"),
    ("cloudSync.pulling", "拉取中...", "Pulling…"),
    ("cloudSync.pullingStatus", "正在拉取...", "Pulling…"),
    ("cloudSync.pullDone", "拉取完成", "Pull complete"),
    ("cloudSync.pullFailed", "拉取失败", "Pull failed"),
    ("cloudSync.pullFailedMsg", "拉取失败：{message}", "Pull failed: {message}"),
    ("cloudSync.disconnectDone", "已断开连接", "Disconnected"),
    ("cloudSync.disconnectFailed", "断开失败", "Disconnect failed"),
    ("cloudSync.disconnectFailedMsg", "断开失败：{message}", "Disconnect failed: {message}"),
    # tags
    ("tags.changeName", "更改名称", "Rename"),
    ("tags.deleteTag", "删除标签", "Delete tag"),
    ("tags.addFailed", "添加标签失败: ", "Add tag failed: "),
    ("tags.renameFailed", "重命名标签失败: ", "Rename tag failed: "),
    (
        "tags.confirmDelete",
        "确定要删除标签「{name}」吗？\n\n该标签将从所有文件的 YAML tags 中移除，同时更新 WIKI.md。",
        'Delete tag "{name}"?\n\nRemoves from all file YAML tags and updates WIKI.md.',
    ),
    ("tags.deleteFailed", "删除标签失败: ", "Delete tag failed: "),
    ("tags.deleteError", "删除标签出错", "Delete tag error"),
    ("tags.createFailed", "创建标签失败: ", "Create tag failed: "),
    ("tags.createError", "创建标签出错: ", "Create tag error: "),
    # links
    ("links.title", "双向链接", "Bidirectional links"),
    ("links.loadFailed", "无法加载链接数据", "Could not load links"),
    ("links.empty", "暂无链接", "No links yet"),
    ("links.configureApiKey", "请先在设置中配置 API Key", "Configure API Key in Settings first"),
    ("links.apiConfigFailed", "无法获取 API 配置: ", "Could not load API config: "),
    ("links.checking", "检查中", "Checking…"),
    ("links.testingApi", "正在测试 API 连接", "Testing API connection…"),
    ("links.apiFailed", "API 连接失败: ", "API connection failed: "),
    ("links.apiTestError", "API 连接测试出错: ", "API test error: "),
    ("links.analyzing", "分析中", "Analyzing…"),
    ("links.buildingPairs", "正在读取文件并构建候选对", "Reading files and building candidate pairs…"),
    (
        "links.discoverDone",
        "完成：扫描 {files} 个文件，发现 {count} 个新关联",
        "Done: scanned {files} files, found {count} new links",
    ),
    ("links.discoverNone", "完成：扫描 {files} 个文件，未发现新关联", "Done: scanned {files} files, no new links"),
    ("links.discoverFailed", "发现失败", "Discovery failed"),
    ("links.startFailed", "启动失败", "Start failed"),
    # preview
    ("preview.loading", "加载中...", "Loading…"),
    ("preview.typeWord", "Word 文档", "Word document"),
    ("preview.loadFailed", "加载失败", "Load failed"),
    ("preview.cannotRead", "无法读取文件", "Could not read file"),
    ("preview.prevPage", "上一页", "Previous page"),
    ("preview.nextPage", "下一页", "Next page"),
    ("preview.zoomOut", "缩小", "Zoom out"),
    ("preview.zoomIn", "放大", "Zoom in"),
    ("preview.pdfViewerMissing", "PDF 查看器未加载", "PDF viewer not loaded"),
    ("preview.pdfJsUnavailable", "pdf.js 库不可用，请检查网络连接", "pdf.js unavailable — check network"),
    ("preview.pdfLoadFailed", "PDF 加载失败", "PDF load failed"),
    ("preview.typeLabel", "类型:", "Type:"),
    ("preview.unknownType", "未知", "Unknown"),
    ("preview.sizeLabel", "大小:", "Size:"),
    ("preview.modifiedLabel", "修改时间:", "Modified:"),
    ("preview.docxEmpty", "（文档无可见正文）", "(No visible document body)"),
    ("preview.defaultName", "预览", "Preview"),
    # ingest
    ("ingest.stage.schema", "规范", "Schema"),
    ("ingest.stage.convert", "转换", "Convert"),
    ("ingest.stage.classify", "分类", "Classify"),
    ("ingest.stage.index", "向量索引", "Index"),
    ("ingest.stage.cascade", "综述", "Survey"),
    ("ingest.stage.lint", "健康检查", "Health check"),
    ("ingest.stage.sync", "同步", "Sync"),
    ("ingest.pipelineRunning", "入库流水线", "Ingest pipeline"),
    ("ingest.cancelled", "入库已取消", "Ingest cancelled"),
    ("ingest.done", "入库完成", "Ingest complete"),
    ("ingest.failed", "入库失败: ", "Ingest failed: "),
    ("ingest.starting", "启动入库流水线…", "Starting ingest pipeline…"),
    ("ingest.statConverted", "转换 {count}", "converted {count}"),
    ("ingest.statClassified", "分类 {count}", "classified {count}"),
    ("ingest.statIndexed", "索引 {count}", "indexed {count}"),
    ("ingest.statCascade", "综述 {count}", "surveys {count}"),
    # download
    ("download.done", "下载完成：{success}/{total} 篇成功", "Download done: {success}/{total} succeeded"),
    ("download.failed", "下载失败：{message}", "Download failed: {message}"),
    ("download.enterUrl", "请输入至少一个 URL", "Enter at least one URL"),
    ("download.taskRunning", "下载任务正在进行中，请稍后", "Download in progress — please wait"),
    ("download.preparing", "正在准备下载...", "Preparing download…"),
    ("download.progress", "正在下载第 {current}/{total} 篇...", "Downloading {current}/{total}…"),
    ("download.error", "下载出错: {message}", "Download error: {message}"),
    ("download.downloading", "下载中", "Downloading…"),
    ("download.enterUrlSingle", "请输入要下载的 URL", "Enter URL to download"),
    ("download.waiting", "正在下载，请稍候", "Downloading — please wait"),
    # integrator
    ("integrator.extractingTopics", "正在提取主题", "Extracting topics…"),
    ("integrator.extracting", "提取中", "Extracting…"),
    ("integrator.readingFileList", "正在读取文件列表", "Reading file list…"),
    ("integrator.writingTopics", "正在写入主题列表", "Writing topic list…"),
    ("integrator.showTopic", "显示主题 {current}/{total}: {topic}", "Topic {current}/{total}: {topic}"),
    ("integrator.extractDone", "提取完成，共 {count} 个主题", "Extracted {count} topics"),
    ("integrator.extractFailed", "提取失败", "Extract failed"),
    ("integrator.extractTopicsFailed", "提取主题失败: ", "Extract topics failed: "),
    ("integrator.integrating", "整合中", "Integrating…"),
    ("integrator.integratingStatus", "正在整合", "Integrating…"),
    ("integrator.preparing", "正在准备整合...", "Preparing integration…"),
    ("integrator.integrateDone", "整合完成", "Integration complete"),
    ("integrator.integrateFailed", "整合失败：{message}", "Integration failed: {message}"),
    ("integrator.integratingWait", "正在整合，请稍候", "Integrating — please wait"),
    ("integrator.integrateFailedShort", "整合失败: ", "Integration failed: "),
    # theme about (modal)
    ("about.version", "版本 1.0.0", "Version 1.0.0"),
    ("about.desc", "AI 驱动的 Markdown 笔记知识库管理工具", "AI-powered Markdown knowledge base"),
    ("about.coreFeatures", "核心功能", "Core features"),
    ("about.feature1", "Markdown 笔记管理与编辑", "Markdown note management & editing"),
    ("about.feature2", "AI 智能主题分析与归类", "AI topic analysis & classification"),
    ("about.feature3", "AI 主题综述自动撰写", "AI topic survey generation"),
    ("about.feature4", "标签管理与自动匹配", "Tag management & auto-matching"),
    ("about.feature5", "双向链接发现与可视化", "Bidirectional link discovery & graph"),
    ("about.feature6", "网络文章批量下载与转换", "Batch web download & conversion"),
    ("about.feature7", "多格式文件导入与整合", "Multi-format import & integration"),
    ("about.feature8", "AI 改写与格式化", "AI rewrite & formatting"),
    ("about.techArchitecture", "技术架构", "Architecture"),
    ("about.techFrontend", "前端：Tauri v2 + HTML / CSS / JS", "Frontend: Tauri v2 + HTML / CSS / JS"),
    ("about.techBackend", "后端：Python sidecar", "Backend: Python sidecar"),
    ("about.techEditor", "编辑器：Tiptap", "Editor: Tiptap"),
    ("about.techLlm", "大模型：LangChain + ChatOpenAI", "LLM: LangChain + ChatOpenAI"),
    ("about.author", "作者：四海", "Author: Sihai"),
    ("about.opensource", "开源项目 · GitHub: Miles128/NoteAI", "Open source · GitHub: Miles128/NoteAI"),
    ("download.reasonPrefix", "   原因: ", "   Reason: "),
    ("search.unavailable", "搜索不可用", "Search unavailable"),
    ("search.loading", "搜索中...", "Searching…"),
    ("search.failed", "搜索失败", "Search failed"),
    ("search.error", "搜索出错: {message}", "Search error: {message}"),
    ("search.noResults", '未找到匹配 "{query}" 的笔记', 'No notes matching "{query}"'),
    ("search.resultCount", "{count} 个结果", "{count} results"),
    ("search.resultTruncated", "前 50 个结果（共 {total} 个）", "Top 50 of {total} results"),
    ("editor.saveLoading", "加载中...", "Loading…"),
    ("editor.saveSaved", "已保存", "Saved"),
    ("editor.saveSavedSimple", "已保存(简易模式)", "Saved (simple mode)"),
    ("editor.previewParseError", "预览解析出错", "Preview parse error"),
    ("editor.surveyEmbed", "📄 {topic} 综述", "📄 {topic} survey"),
    ("editor.saving", "保存中...", "Saving…"),
    ("editor.saveFailed", "保存失败", "Save failed"),
]


def _set_nested(d: dict, key: str, value: str) -> None:
    parts = key.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def build_locales() -> tuple[dict, dict]:
    zh: dict = {}
    en: dict = {}
    for key, z, e in CATALOG:
        _set_nested(zh, key, z)
        _set_nested(en, key, e)
    return zh, en


def patch_html() -> None:
    """Add data-i18n attributes to index.html static UI strings."""
    html = HTML.read_text(encoding="utf-8")
    # title attributes: title="中文" -> data-i18n-title="key"
    title_map = {
        "网页下载": "titlebar.webDownload",
        "导入文件": "titlebar.importFiles",
        "打开工作区": "titlebar.openWorkspace",
        "目录树": "titlebar.tree",
        "标签": "titlebar.tags",
        "双向链接": "titlebar.links",
        "关闭预览": "titlebar.closePreview",
        "待处理": "titlebar.pending",
        "AI 助手": "titlebar.aiAssistant",
        "编辑": "titlebar.edit",
        "关系图谱": "titlebar.relationGraph",
        "搜索 (Cmd+K)": "titlebar.search",
        "设置": "titlebar.settings",
        "展开侧边栏": "titlebar.expandSidebar",
        "取消": "common.cancel",
        "关闭": "common.close",
        "确认创建标签": "sidebar.confirmCreateTag",
        "收起侧边栏": "sidebar.collapse",
        "新建主题": "sidebar.newTopic",
        "新建笔记": "sidebar.newNote",
        "自动匹配标签：扫描文件标题匹配已有标签": "sidebar.autoTagTitle",
        "新加标签：创建新的标签分类": "sidebar.addTagTitle",
        "发现链接：AI 分析文章关联": "sidebar.discoverLinksTitle",
        "重新扫描断链、孤儿页、过时综述": "pending.healthCheck",
        "重试所有综述更新失败项": "pending.retryAllSurveys",
        "显示/隐藏文件名": "graph.toggleFilenames",
        "放大": "graph.zoomIn",
        "缩小": "graph.zoomOut",
        "重放动画": "graph.replay",
        "刷新图谱": "graph.refresh",
        "布局参数": "graph.layoutSettings",
        "关闭图谱": "graph.close",
        "收起": "common.collapse",
        "一键确认所有待确认链接": "links.confirmAll",
        "加粗": "editor.bold",
        "斜体": "editor.italic",
        "删除线": "editor.strike",
        "行内代码": "editor.inlineCode",
        "标题 1": "editor.heading1",
        "标题 2": "editor.heading2",
        "标题 3": "editor.heading3",
        "无序列表": "editor.bulletList",
        "有序列表": "editor.orderedList",
        "任务列表": "editor.taskList",
        "引用": "editor.blockquote",
        "代码块": "editor.codeBlock",
        "链接": "editor.link",
        "图片": "editor.image",
        "撤销": "editor.undo",
        "重做": "editor.redo",
        "LLM 改写：用中立客观风格重写文档": "editor.llmRewrite",
        "在设置 → 小忆助手中切换": "assistant.mode.badgeHint",
        "发送": "assistant.send",
        "重新入库": "ingest.retryTitle",
        "取消入库": "ingest.cancelTitle",
    }
    for title, key in title_map.items():
        html = html.replace(f'title="{title}"', f'data-i18n-title="{key}"')

    # Replace inner text with data-i18n on parent tags (clear hardcoded text)
    replacements = [
        ('<div class="tree-empty">暂无工作区</div>', '<div class="tree-empty" data-i18n="common.noWorkspace"></div>'),
        ("<h2>待处理</h2>", '<h2 data-i18n="pending.title"></h2>'),
        (
            '<span class="pending-view-count" id="pending-view-count">0 项</span>',
            '<span class="pending-view-count" id="pending-view-count" data-i18n="common.pendingCount" data-i18n-count="0"></span>',
        ),
        (
            '<button type="button" class="pending-header-btn" id="pending-lint-run-btn"',
            '<button type="button" class="pending-header-btn" id="pending-lint-run-btn" data-i18n="pending.healthCheck"',
        ),
        (">健康检查</button>", "></button>"),
        (
            'id="pending-cascade-retry-all-btn" title="重试所有综述更新失败项">全部重试综述</button>',
            'id="pending-cascade-retry-all-btn" data-i18n-title="pending.retryAllSurveys" data-i18n="pending.retryAllSurveys"></button>',
        ),
        (
            '<p class="pending-view-hint">主题/链接确认、综述失败、转换失败与健康检查问题，统一在此处理。</p>',
            '<p class="pending-view-hint" data-i18n="pending.hint"></p>',
        ),
        (
            '<div class="pending-view-empty">没有待处理的事项</div>',
            '<div class="pending-view-empty" data-i18n="pending.empty"></div>',
        ),
        ('<div class="card-title">笔记整合</div>', '<div class="card-title" data-i18n="integrator.cardTitle"></div>'),
        (
            '<span class="status-text">从Notes文件夹读取markdown文件，整合输出到Abstract文件夹</span>',
            '<span class="status-text" data-i18n="integrator.statusLine"></span>',
        ),
        (
            '<div class="card-title">主题设置</div>',
            '<div class="card-title" data-i18n="integrator.topicSettings"></div>',
        ),
        (
            '<div class="graph-empty" id="graph-empty" style="display:none;">暂无数据</div>',
            '<div class="graph-empty" id="graph-empty" style="display:none;" data-i18n="graph.empty"></div>',
        ),
        (
            '<div class="graph-loading" id="graph-loading" style="display:none;">加载中...</div>',
            '<div class="graph-loading" id="graph-loading" style="display:none;" data-i18n="graph.loading"></div>',
        ),
        (
            '<span class="ai-panel-header-title">小忆助手</span>',
            '<span class="ai-panel-header-title" data-i18n="assistant.panelTitle"></span>',
        ),
        (
            '<span class="ai-mode-badge" id="ai-mode-badge" title="在设置 → 小忆助手中切换">问答模式</span>',
            '<span class="ai-mode-badge" id="ai-mode-badge" data-i18n-title="assistant.mode.badgeHint" data-i18n="assistant.mode.qa"></span>',
        ),
        ("<h2>设置</h2>", '<h2 data-i18n="settings.title"></h2>'),
        (
            '<span id="ingest-pipeline-stage">入库</span>',
            '<span class="ingest-label" id="ingest-pipeline-stage" data-i18n="ingest.label"></span>',
        ),
    ]
    for old, new in replacements:
        if old in html:
            html = html.replace(old, new)

    html_replacements = [
        (
            '<span class="sidebar-footer-status" id="sidebar-status-tree">0 篇笔记</span>',
            '<span class="sidebar-footer-status" id="sidebar-status-tree" data-i18n="common.notesCount" data-i18n-count="0"></span>',
        ),
        (
            '<span class="sidebar-footer-status" id="sidebar-status-tags">0 个标签</span>',
            '<span class="sidebar-footer-status" id="sidebar-status-tags" data-i18n="common.tagsCount" data-i18n-count="0"></span>',
        ),
        (
            '<span class="sidebar-footer-status" id="sidebar-status-graph">0 个链接</span>',
            '<span class="sidebar-footer-status" id="sidebar-status-graph" data-i18n="common.linksCount" data-i18n-count="0"></span>',
        ),
        (
            '<div class="form-label">主题个数（留空则自动选择）</div>',
            '<div class="form-label" data-i18n="integrator.topicCount"></div>',
        ),
        (
            '<div class="form-label">点击提取主题，或手动输入（每行一个）</div>',
            '<div class="form-label" data-i18n="integrator.topicListHint"></div>',
        ),
        ('placeholder="主题1&#10;主题2&#10;主题3"', 'data-i18n-placeholder="integrator.topicListPlaceholder"'),
        (
            'title="提取主题：从网页内容中提取关键主题">提取主题</button>',
            'data-i18n-title="integrator.extractTopicsHint" data-i18n="integrator.extractTopics"></button>',
        ),
        (
            'title="开始整合：将内容整合到笔记中">开始整合</button>',
            'data-i18n-title="integrator.startHint" data-i18n="integrator.start"></button>',
        ),
        (
            '<span class="graph-stats-item"><span id="graph-stat-notes">0</span> 笔记</span>',
            '<span class="graph-stats-item"><span id="graph-stat-notes">0</span><span data-i18n="graph.stats.notesSuffix"></span></span>',
        ),
        (
            '<span class="graph-stats-item"><span id="graph-stat-topics">0</span> 主题</span>',
            '<span class="graph-stats-item"><span id="graph-stat-topics">0</span><span data-i18n="graph.stats.topicsSuffix"></span></span>',
        ),
        ('title="一级/二级主题中有综述的占比">综述 ', 'data-i18n-title="graph.stats.surveyHint">综述 '),
        ('title="每篇笔记平均出链数">均链 ', 'data-i18n-title="graph.stats.avgLinksHint">均链 '),
        ('title="Lint 问题总数">Lint ', 'data-i18n-title="graph.stats.lintHint">Lint '),
        (
            '<button class="graph-filter-btn active" data-filter="topic">主题</button>',
            '<button class="graph-filter-btn active" data-filter="topic" data-i18n="graph.filter.topic"></button>',
        ),
        (
            '<button class="graph-filter-btn" data-filter="tag">标签</button>',
            '<button class="graph-filter-btn" data-filter="tag" data-i18n="graph.filter.tag"></button>',
        ),
        (
            '<button class="graph-filter-btn" data-filter="all">全部</button>',
            '<button class="graph-filter-btn" data-filter="all" data-i18n="graph.filter.all"></button>',
        ),
        (
            '<h3 id="graph-settings-title">布局参数</h3>',
            '<h3 id="graph-settings-title" data-i18n="graph.layoutSettings"></h3>',
        ),
        (
            '<button type="button" class="graph-settings-btn" onclick="graphResetLayoutSettings()">恢复默认</button>',
            '<button type="button" class="graph-settings-btn" onclick="graphResetLayoutSettings()" data-i18n="common.resetDefault"></button>',
        ),
        (
            '<button type="button" class="graph-settings-btn graph-settings-btn-primary" onclick="graphApplyLayoutSettings()">应用</button>',
            '<button type="button" class="graph-settings-btn graph-settings-btn-primary" onclick="graphApplyLayoutSettings()" data-i18n="common.apply"></button>',
        ),
        (
            '<span class="pending-links-title">待确认链接</span>',
            '<span class="pending-links-title" data-i18n="links.pendingTitle"></span>',
        ),
        (
            'onclick="onConfirmAllLinks()" data-i18n-title="links.confirmAll">全部确认</button>',
            'onclick="onConfirmAllLinks()" data-i18n-title="links.confirmAll" data-i18n="links.confirmAllBtn"></button>',
        ),
        (
            '<div class="pending-links-empty" id="pending-links-empty">暂无待确认链接</div>',
            '<div class="pending-links-empty" id="pending-links-empty" data-i18n="links.pendingEmpty"></div>',
        ),
        ("<div>选择文件以预览</div>", '<div data-i18n="preview.selectFile"></div>'),
        (
            '<span class="ai-mode-badge" id="ai-mode-badge" data-i18n-title="assistant.mode.badgeHint">问答模式</span>',
            '<span class="ai-mode-badge" id="ai-mode-badge" data-i18n-title="assistant.mode.badgeHint" data-i18n="assistant.mode.qa"></span>',
        ),
        (
            '<div class="form-field flex-1"><div class="form-label">模型</div>',
            '<div class="form-field flex-1"><div class="form-label" data-i18n="settings.modelLabel"></div>',
        ),
        ('<div class="form-label">最大 Tokens</div>', '<div class="form-label" data-i18n="settings.maxTokens"></div>'),
        ('<div class="form-label">最大上下文</div>', '<div class="form-label" data-i18n="settings.maxContext"></div>'),
        ('<div class="form-label">思考链</div>', '<div class="form-label" data-i18n="settings.thinkingChain"></div>'),
        (
            '<button class="btn btn-primary" onclick="saveApiConfig()">保存配置</button>',
            '<button class="btn btn-primary" onclick="saveApiConfig()" data-i18n="settings.saveConfig"></button>',
        ),
        ('<div class="card-title">主题</div>', '<div class="card-title" data-i18n="settings.theme"></div>'),
        ("<span>浅色</span>", '<span data-i18n="settings.themeLight"></span>'),
        ("<span>深色</span>", '<span data-i18n="settings.themeDark"></span>'),
        ("<span>纸质</span>", '<span data-i18n="settings.themePaper"></span>'),
        ("<span>跟随系统</span>", '<span data-i18n="settings.themeSystem"></span>'),
        (
            '<span>小</span>\n                                        <span style="color:var(--text-muted);font-size:12px">（默认）</span>',
            '<span data-i18n="settings.fontSmall"></span>\n                                        <span style="color:var(--text-muted);font-size:12px" data-i18n="settings.fontSmallHint"></span>',
        ),
        (
            '<span>中</span>\n                                        <span style="color:var(--text-muted);font-size:12px">（+2pt）</span>',
            '<span data-i18n="settings.fontMedium"></span>\n                                        <span style="color:var(--text-muted);font-size:12px" data-i18n="settings.fontMediumHint"></span>',
        ),
        (
            '<span>大</span>\n                                        <span style="color:var(--text-muted);font-size:12px">（+4pt）</span>',
            '<span data-i18n="settings.fontLarge"></span>\n                                        <span style="color:var(--text-muted);font-size:12px" data-i18n="settings.fontLargeHint"></span>',
        ),
        ('<div class="card-title">实验功能</div>', '<div class="card-title" data-i18n="settings.experimental"></div>'),
        ("<span>启用云盘同步（实验）</span>", '<span data-i18n="settings.cloudSyncExperimental"></span>'),
        (
            '<p class="settings-hint">默认关闭。开启后设置侧栏显示「云盘同步」。</p>',
            '<p class="settings-hint" data-i18n="settings.cloudSyncExperimentalHint"></p>',
        ),
        (
            '<div class="download-modal-title">下载</div>',
            '<div class="download-modal-title" data-i18n="download.title"></div>',
        ),
        (
            '<button type="button" class="multi-source-tab active" data-ms-tab="url">网页</button>',
            '<button type="button" class="multi-source-tab active" data-ms-tab="url" data-i18n="download.tabWeb"></button>',
        ),
        (
            '<button type="button" class="multi-source-tab" data-ms-tab="rss">RSS</button>',
            '<button type="button" class="multi-source-tab" data-ms-tab="rss" data-i18n="download.tabRss"></button>',
        ),
        (
            '<button type="button" class="multi-source-tab" data-ms-tab="transcript">转录</button>',
            '<button type="button" class="multi-source-tab" data-ms-tab="transcript" data-i18n="download.tabTranscript"></button>',
        ),
        ("<label>条数 <input", '<label><span data-i18n="download.rssCount"></span> <input'),
        (
            '<label><input type="checkbox" id="ms-rss-fetch" checked> 抓取原文</label>',
            '<label><input type="checkbox" id="ms-rss-fetch" checked> <span data-i18n="download.rssFetch"></span></label>',
        ),
        ('id="ms-rss-import-btn">导入 RSS</button>', 'id="ms-rss-import-btn" data-i18n="download.importRss"></button>'),
        (
            'id="ms-transcript-import-btn" style="margin-top:8px">保存转录</button>',
            'id="ms-transcript-import-btn" style="margin-top:8px" data-i18n="download.saveTranscript"></button>',
        ),
        (
            '<span class="switch-label">包含图片的外部 URL 链接</span>',
            '<span class="switch-label" data-i18n="download.includeImages"></span>',
        ),
        (
            'id="modal-download-btn" onclick="startDownloadFromModal()">开始下载</button>',
            'id="modal-download-btn" onclick="startDownloadFromModal()" data-i18n="download.start"></button>',
        ),
        ('id="custom-confirm-cancel"', 'id="custom-confirm-cancel" data-i18n="confirm.cancel"'),
        ('id="custom-confirm-ok"', 'id="custom-confirm-ok" data-i18n="confirm.ok"'),
        (
            'id="ingest-pipeline-retry" data-i18n-title="ingest.retryTitle">重试</button>',
            'id="ingest-pipeline-retry" data-i18n-title="ingest.retryTitle" data-i18n="ingest.retry"></button>',
        ),
        (
            'id="ingest-pipeline-cancel" data-i18n-title="ingest.cancelTitle">取消</button>',
            'id="ingest-pipeline-cancel" data-i18n-title="ingest.cancelTitle" data-i18n="common.cancel"></button>',
        ),
    ]
    for old, new in html_replacements:
        if old in html:
            html = html.replace(old, new)

    # Settings tabs (rich HTML)
    settings_html = [
        (
            '<div class="card-title">工作区 Schema</div>',
            '<div class="card-title" data-i18n="settings.schemaTitle"></div>',
        ),
        (
            '<p class="settings-hint">定义 AI 可写范围、主题层级与冲突策略（<code>schema.md</code>）。</p>',
            '<p class="settings-hint" data-i18n="settings.schemaHint"></p>',
        ),
        (
            'id="settings-schema-wizard-btn">配置向导</button>',
            'id="settings-schema-wizard-btn" data-i18n="settings.schemaWizardBtn"></button>',
        ),
        (
            'id="settings-schema-reload-btn">重新加载</button>',
            'id="settings-schema-reload-btn" data-i18n="settings.schemaReloadBtn"></button>',
        ),
        ('placeholder="schema.md 内容…"', 'data-i18n-placeholder="settings.schemaEditorPlaceholder"'),
        (
            'id="settings-schema-save-btn" style="margin-top:12px">保存 Schema</button>',
            'id="settings-schema-save-btn" style="margin-top:12px" data-i18n="settings.schemaSaveBtn"></button>',
        ),
        (
            '<div class="card-title">资料维护</div>',
            '<div class="card-title" data-i18n="settings.maintenanceTitle"></div>',
        ),
        (
            '<p class="settings-hint">重新转换 <code>Raw/</code> 下支持的 PDF、Word 等原件，生成 Markdown 笔记。</p>',
            '<p class="settings-hint" data-i18n="settings.maintenanceHint"></p>',
        ),
        (
            'id="settings-raw-convert-btn">Raw 批量重转</button>',
            'id="settings-raw-convert-btn" data-i18n="settings.rawConvertBtn"></button>',
        ),
        (
            '<div class="card-title">小忆助手</div>',
            '<div class="card-title" data-i18n="settings.assistantIntroTitle"></div>',
        ),
        (
            '<div class="card-title">助手模式</div>',
            '<div class="card-title" data-i18n="settings.agentModeTitle"></div>',
        ),
        (
            '<span class="settings-toggle-label">开启助手模式</span>',
            '<span class="settings-toggle-label" data-i18n="settings.agentModeLabel"></span>',
        ),
        (
            '<span class="settings-toggle-desc">关闭时仅问答与只读查询；开启后可新建主题、移动笔记、更新综述等</span>',
            '<span class="settings-toggle-desc" data-i18n="settings.agentModeDesc"></span>',
        ),
        ('<div class="card-title">用户画像</div>', '<div class="card-title" data-i18n="settings.profileTitle"></div>'),
        (
            '<p class="settings-hint">用 Markdown 描述你的背景与偏好，小忆会在问答和助手模式中参考这些内容调整回答风格。</p>',
            '<p class="settings-hint" data-i18n="settings.profileHint"></p>',
        ),
        (
            'placeholder="## 关于我&#10;&#10;- 职业：AI产品经理',
            'data-i18n-placeholder="settings.profilePlaceholder" data-profile-placeholder="1" placeholder="## 关于我&#10;&#10;- 职业：AI产品经理',
        ),
        (
            'onclick="saveUserProfile()">保存画像</button>',
            'onclick="saveUserProfile()" data-i18n="settings.profileSaveBtn"></button>',
        ),
        ('<div class="card-title">知识库索引</div>', '<div class="card-title" data-i18n="settings.indexTitle"></div>'),
        (
            '<p class="settings-hint">问答依赖向量索引。日常入库会自动维护；若检索结果明显不对，可手动全量重建（耗时较长，请在工作区空闲时操作）。</p>',
            '<p class="settings-hint" data-i18n="settings.indexHint"></p>',
        ),
        (
            'id="settings-assistant-rebuild-index-btn">重建知识库索引</button>',
            'id="settings-assistant-rebuild-index-btn" data-i18n="settings.rebuildIndexBtn"></button>',
        ),
        (
            '<div class="card-title">操作记录</div>',
            '<div class="card-title" data-i18n="settings.activityLogTitle"></div>',
        ),
        (
            '<p class="settings-hint settings-activity-log-hint">工作区内 AI 与入库操作，写入 <code>wiki/log.md</code>。健康检查会自动删除断链、更新过时综述。</p>',
            '<p class="settings-hint settings-activity-log-hint" data-i18n="settings.activityLogHint"></p>',
        ),
        (
            '<div class="settings-activity-log-empty">加载中…</div>',
            '<div class="settings-activity-log-empty" data-i18n="settings.activityLogLoading"></div>',
        ),
        (
            "<p>NoteAI 是一款智能知识管理工具，帮助用户高效组织和管理 Markdown 笔记。</p>",
            '<p data-i18n="settings.aboutDesc"></p>',
        ),
        (
            '<p style="margin-top:12px"><strong>功能：</strong></p>',
            '<p style="margin-top:12px"><strong data-i18n="settings.aboutFeatures"></strong></p>',
        ),
        ("<li>多层主题树知识图谱</li>", '<li data-i18n="settings.aboutFeature1"></li>'),
        ("<li>AI 辅助写作与内容整合</li>", '<li data-i18n="settings.aboutFeature2"></li>'),
        ("<li>网页内容下载与分析</li>", '<li data-i18n="settings.aboutFeature3"></li>'),
        ("<li>标签与双向链接管理</li>", '<li data-i18n="settings.aboutFeature4"></li>'),
        (
            '<p style="margin-top:16px"><strong>技术栈：</strong>Tauri v2 + Python Sidecar + D3.js</p>',
            '<p style="margin-top:16px"><strong data-i18n="settings.aboutTech"></strong> <span data-i18n="settings.aboutTechLine"></span></p>',
        ),
        (
            '<p style="margin-top:8px">基于 Rust 构建桌面端，Python 提供 AI 能力，D3.js 渲染知识图谱。</p>',
            '<p style="margin-top:8px" data-i18n="settings.aboutTechDesc"></p>',
        ),
    ]
    for old, new in settings_html:
        if old in html:
            html = html.replace(old, new)

    assistant_intro = [
        (
            '<p class="settings-hint">小忆是你的知识库问答伙伴。默认<strong>问答模式</strong>下，她会检索笔记与综述来回答，并可<strong>搜索笔记、查看主题列表</strong>，无需开启助手模式。</p>',
            '<p class="settings-hint" data-i18n-html="settings.assistantIntro1"></p>',
        ),
        (
            '<p class="settings-hint" style="margin-top:8px">开启<strong>助手模式</strong>后，小忆还可以在你的工作区里<strong>动手修改</strong>，例如：</p>',
            '<p class="settings-hint" style="margin-top:8px" data-i18n-html="settings.assistantIntro2"></p>',
        ),
        (
            "<li><strong>新建主题</strong> — 可建一级或二级主题；二级主题必须您明确指定所属一级，小忆不会自动猜测</li>",
            '<li data-i18n-html="settings.assistantCap1"></li>',
        ),
        (
            "<li><strong>移动笔记</strong> — 把某篇笔记归到指定主题下</li>",
            '<li data-i18n-html="settings.assistantCap2"></li>',
        ),
        (
            "<li><strong>更新综述</strong> — 为某个主题重新生成或刷新主题综述</li>",
            '<li data-i18n-html="settings.assistantCap3"></li>',
        ),
        (
            "<li><strong>整理知识库</strong> — 在需要时触发入库流水线（转换、分类、索引等）</li>",
            '<li data-i18n-html="settings.assistantCap4"></li>',
        ),
        (
            '<p class="settings-hint">问答模式下也可随时说「有哪些主题」「搜一下 xxx 相关的笔记」。助手模式会逐步执行写操作并在对话里显示进度。LLM 接口请在「模型」分页配置。</p>',
            '<p class="settings-hint" data-i18n="settings.assistantIntro3"></p>',
        ),
    ]
    for old, new in assistant_intro:
        if old in html:
            html = html.replace(old, new)

    # quick create modal
    qc = [
        (
            '<span id="quick-create-title">快速新建</span>',
            '<span id="quick-create-title" data-i18n="quickCreate.title"></span>',
        ),
        (
            '<button type="button" class="qc-tab active" data-qc-tab="note">新建笔记</button>',
            '<button type="button" class="qc-tab active" data-qc-tab="note" data-i18n="quickCreate.tabNote"></button>',
        ),
        (
            '<button type="button" class="qc-tab" data-qc-tab="topic">新建主题</button>',
            '<button type="button" class="qc-tab" data-qc-tab="topic" data-i18n="quickCreate.tabTopic"></button>',
        ),
        ('<label class="qc-label">标题</label>', '<label class="qc-label" data-i18n="quickCreate.noteTitle"></label>'),
        (
            '<label class="qc-label">主题（可选）</label>',
            '<label class="qc-label" data-i18n="quickCreate.noteTopic"></label>',
        ),
        (
            '<p class="qc-hint">未选主题时保存到 Notes/_未分类/</p>',
            '<p class="qc-hint" data-i18n="quickCreate.noteUncategorizedHint"></p>',
        ),
        (
            'id="qc-note-submit">创建并打开</button>',
            'id="qc-note-submit" data-i18n="quickCreate.createAndOpen"></button>',
        ),
        (
            '<label class="qc-label">主题名称</label>',
            '<label class="qc-label" data-i18n="quickCreate.topicName"></label>',
        ),
        (
            '<label class="qc-label">上级主题（可选）</label>',
            '<label class="qc-label" data-i18n="quickCreate.topicParent"></label>',
        ),
        (
            '<p class="qc-hint">有上级时创建为「上级 &gt; 名称」</p>',
            '<p class="qc-hint" data-i18n="quickCreate.topicParentHint"></p>',
        ),
        (
            'id="qc-topic-submit">创建主题</button>',
            'id="qc-topic-submit" data-i18n="quickCreate.createTopic"></button>',
        ),
    ]
    for old, new in qc:
        if old in html:
            html = html.replace(old, new)

    schema_html = [
        ("<h3>配置工作区 Schema</h3>", '<h3 data-i18n="schemaWizard.modalTitle"></h3>'),
        ("<h4>这个工作区主要做什么？</h4>", '<h4 data-i18n="schemaWizard.stepPurpose"></h4>'),
        (
            '<p class="hint">决定目录说明与整理语气的默认表述。</p>',
            '<p class="hint" data-i18n="schemaWizard.stepPurposeHint"></p>',
        ),
        ("<span>个人知识库 — 长期积累、学习笔记</span>", '<span data-i18n="schemaWizard.purposePersonal"></span>'),
        ("<span>项目文档库 — 围绕单一产品/课题</span>", '<span data-i18n="schemaWizard.purposeProject"></span>'),
        ("<span>研究资料库 — 论文、报告、摘录为主</span>", '<span data-i18n="schemaWizard.purposeResearch"></span>'),
        ("<h4>关注哪些知识领域？</h4>", '<h4 data-i18n="schemaWizard.stepDomains"></h4>'),
        (
            '<p class="hint">可多选，将生成一级主题示例（可在 project_rules 中再改）。</p>',
            '<p class="hint" data-i18n="schemaWizard.stepDomainsHint"></p>',
        ),
        (
            'value="rag" checked> RAG 与检索</label>',
            'value="rag" checked> <span data-i18n="schemaWizard.domainRag"></span></label>',
        ),
        (
            'value="product" checked> AI 产品</label>',
            'value="product" checked> <span data-i18n="schemaWizard.domainProduct"></span></label>',
        ),
        ('value="llm"> 大模型应用</label>', 'value="llm"> <span data-i18n="schemaWizard.domainLlm"></span></label>'),
        (
            'value="tools"> 工具与效率</label>',
            'value="tools"> <span data-i18n="schemaWizard.domainTools"></span></label>',
        ),
        (
            'value="career"> 职业成长</label>',
            'value="career"> <span data-i18n="schemaWizard.domainCareer"></span></label>',
        ),
        (
            'placeholder="其他一级主题，逗号分隔，如：产品设计, 开源社区"',
            'data-i18n-placeholder="schemaWizard.customDomainsPlaceholder"',
        ),
        ("<h4>主题层级与语言</h4>", '<h4 data-i18n="schemaWizard.stepDepth"></h4>'),
        (
            '<p class="hint">对应 `Notes/` 文件夹深度与命名习惯。</p>',
            '<p class="hint" data-i18n="schemaWizard.stepDepthHint"></p>',
        ),
        ("<span>以两级为主（一级 &gt; 二级）</span>", '<span data-i18n="schemaWizard.depth2"></span>'),
        ("<span>标准三级（一级 &gt; 二级 &gt; 三级）</span>", '<span data-i18n="schemaWizard.depth3"></span>'),
        ("<span>中文优先（文件名、标签、主题）</span>", '<span data-i18n="schemaWizard.langZh"></span>'),
        ("<span>中英混合（专有名词保留英文）</span>", '<span data-i18n="schemaWizard.langMixed"></span>'),
        ("<h4>整理习惯</h4>", '<h4 data-i18n="schemaWizard.stepHabits"></h4>'),
        (
            '<p class="hint">写入 schema.md，约束 AI 自动整理行为。</p>',
            '<p class="hint" data-i18n="schemaWizard.stepHabitsHint"></p>',
        ),
        (
            'value="folder_truth" checked> 文件夹路径是主题唯一依据</label>',
            'value="folder_truth" checked> <span data-i18n="schemaWizard.habitFolderTruth"></span></label>',
        ),
        (
            'value="pending" checked> 不确定分类 → 待办，不硬塞</label>',
            'value="pending" checked> <span data-i18n="schemaWizard.habitPending"></span></label>',
        ),
        (
            'value="survey_only" checked> 级联只更新综述，不改笔记正文</label>',
            'value="survey_only" checked> <span data-i18n="schemaWizard.habitSurveyOnly"></span></label>',
        ),
        (
            'value="auto_convert" checked> 自动转换 PDF/DOCX 等</label>',
            'value="auto_convert" checked> <span data-i18n="schemaWizard.habitAutoConvert"></span></label>',
        ),
        (
            'value="tags_cn" checked> 标签 2～5 个，中文优先</label>',
            'value="tags_cn" checked> <span data-i18n="schemaWizard.habitTagsCn"></span></label>',
        ),
        ("<h4>确认生成的 schema.md</h4>", '<h4 data-i18n="schemaWizard.stepConfirm"></h4>'),
        (
            '<p class="hint">将保存到工作区根目录，并同步生成 project_rules.md。</p>',
            '<p class="hint" data-i18n="schemaWizard.stepConfirmHint"></p>',
        ),
        (
            'id="schema-wizard-use-default">使用推荐默认</button>',
            'id="schema-wizard-use-default" data-i18n="schemaWizard.useDefault"></button>',
        ),
        ('id="schema-wizard-back">上一步</button>', 'id="schema-wizard-back" data-i18n="schemaWizard.back"></button>'),
        ('id="schema-wizard-next">下一步</button>', 'id="schema-wizard-next" data-i18n="schemaWizard.next"></button>'),
        (
            'id="schema-wizard-save" style="display:none">完成并保存</button>',
            'id="schema-wizard-save" style="display:none" data-i18n="schemaWizard.finish"></button>',
        ),
        ("<h3>项目规则</h3>", '<h3 data-i18n="projectRules.title"></h3>'),
        (
            '<p class="modal-desc">定义此工作区的项目规则，AI 在回答问题时会参考这些规则。</p>',
            '<p class="modal-desc" data-i18n="projectRules.desc"></p>',
        ),
        (
            'placeholder="## 项目规则&#10;&#10;- 本项目是关于 XXX 的知识库',
            'data-i18n-placeholder="projectRules.placeholder" placeholder="## 项目规则&#10;&#10;- 本项目是关于 XXX 的知识库',
        ),
        (
            'onclick="closeProjectRulesModal()">跳过</button>',
            'onclick="closeProjectRulesModal()" data-i18n="common.skip"></button>',
        ),
        (
            'onclick="saveProjectRulesModal()">保存规则</button>',
            'onclick="saveProjectRulesModal()" data-i18n="projectRules.save"></button>',
        ),
    ]
    for old, new in schema_html:
        if old in html:
            html = html.replace(old, new)

    # fix confirm buttons - need empty text with data-i18n
    html = html.replace(
        'id="custom-confirm-cancel" data-i18n="confirm.cancel" style=',
        'id="custom-confirm-cancel" data-i18n="confirm.cancel" style=',
    )
    html = html.replace(
        '<button id="custom-confirm-cancel" data-i18n="confirm.cancel" style="background:var(--bg-hover);color:var(--text-muted);border:1px solid var(--border);border-radius:6px;padding:7px 18px;cursor:pointer;font-size:13px">取消</button>',
        '<button id="custom-confirm-cancel" data-i18n="confirm.cancel" style="background:var(--bg-hover);color:var(--text-muted);border:1px solid var(--border);border-radius:6px;padding:7px 18px;cursor:pointer;font-size:13px"></button>',
    )
    html = html.replace(
        '<button id="custom-confirm-ok" data-i18n="confirm.ok" style="background:#4A90D9;color:#fff;border:none;border-radius:6px;padding:7px 18px;cursor:pointer;font-size:13px">确认</button>',
        '<button id="custom-confirm-ok" data-i18n="confirm.ok" style="background:#4A90D9;color:#fff;border:none;border-radius:6px;padding:7px 18px;cursor:pointer;font-size:13px"></button>',
    )

    # Nav/settings spans
    nav_map = {
        'data-tab="model"><svg': 'data-tab="model" data-i18n="settings.nav.model"><svg',
        'data-tab="ui"><svg': 'data-tab="ui" data-i18n="settings.nav.ui"><svg',
        'data-tab="assistant"><svg': 'data-tab="assistant" data-i18n="settings.nav.assistant"><svg',
        'data-tab="activity-log"><svg': 'data-tab="activity-log" data-i18n="settings.nav.activityLog"><svg',
        'data-tab="schema"><svg': 'data-tab="schema" data-i18n="settings.nav.schema"><svg',
        'data-tab="about"><svg': 'data-tab="about" data-i18n="settings.nav.about"><svg',
    }
    # simpler: add data-i18n to span inside nav buttons
    html = html.replace("<span>模型</span>", '<span data-i18n="settings.nav.model"></span>')
    html = html.replace("<span>界面</span>", '<span data-i18n="settings.nav.ui"></span>')
    html = html.replace(
        '<button class="settings-nav-btn" data-tab="assistant">',
        '<button class="settings-nav-btn" data-tab="assistant">',
    )
    html = html.replace("<span>小忆助手</span>", '<span data-i18n="settings.nav.assistant"></span>', 1)
    html = html.replace("<span>操作记录</span>", '<span data-i18n="settings.nav.activityLog"></span>')
    html = html.replace("<span>Schema</span>", '<span data-i18n="settings.nav.schema"></span>')
    html = html.replace("<span>关于</span>", '<span data-i18n="settings.nav.about"></span>')
    html = html.replace("<span>云盘同步</span>", '<span data-i18n="settings.nav.cloudSync"></span>')

    # Remove broken text_map block - use targeted replacements above
    _ = nav_map

    # placeholders
    ph_map = {
        'placeholder="输入标签名称..."': 'data-i18n-placeholder="sidebar.tagPlaceholder"',
        'placeholder="搜索笔记..."': 'data-i18n-placeholder="search.placeholder"',
        'placeholder="主题过滤（含子串）"': 'data-i18n-placeholder="search.filterTopic"',
        'placeholder="标签过滤"': 'data-i18n-placeholder="search.filterTag"',
        'placeholder="每行一个 URL"': 'data-i18n-placeholder="download.urlsPlaceholder"',
        'placeholder="RSS / Atom 订阅地址"': 'data-i18n-placeholder="download.rssPlaceholder"',
        'placeholder="标题"': 'data-i18n-placeholder="download.transcriptTitle"',
        'placeholder="来源（可选）"': 'data-i18n-placeholder="download.transcriptSource"',
        'placeholder="粘贴转录文本…"': 'data-i18n-placeholder="download.transcriptContent"',
        'placeholder="笔记标题"': 'data-i18n-placeholder="quickCreate.noteTitlePlaceholder"',
        'placeholder="例如：Agent 入门"': 'data-i18n-placeholder="quickCreate.topicNamePlaceholder"',
        'placeholder="例如：5"': 'data-i18n-placeholder="integrator.topicCountPlaceholder"',
    }
    for old, attr in ph_map.items():
        html = html.replace(old, attr)

    HTML.write_text(html, encoding="utf-8")
    print("Patched index.html")


def flatten(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


def patch_js_whole_literals(flat: dict[str, str]) -> int:
    """Replace only whole 'text' / \"text\" literals on UI lines."""
    ui_markers = (
        "innerHTML",
        "textContent",
        "placeholder",
        ".title",
        "showStatus",
        "updateStatus",
        "alert(",
        "confirm(",
        "ToastModule",
        "setSidebarStatus",
        "aria-label",
        "badge.textContent",
        "btn.textContent",
    )
    text_to_key = {v: k for k, v in flat.items() if v and len(v) >= 2}
    items = sorted(text_to_key.items(), key=lambda x: -len(x[0]))
    total = 0
    for js_path in sorted(JS_DIR.glob("*.js")):
        if js_path.name in ("i18n.js",):
            continue
        lines = js_path.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = False
        for i, line in enumerate(lines):
            if not any(m in line for m in ui_markers):
                continue
            if "window.t(" in line:
                continue
            new_line = line
            for text, key in items:
                repl = f"window.t('{key}')"
                if repl in new_line:
                    continue
                for q in ("'", '"'):
                    old = f"{q}{text}{q}"
                    if old in new_line and repl not in new_line:
                        new_line = new_line.replace(old, repl)
                        total += 1
            if new_line != line:
                lines[i] = new_line
                changed = True
        if changed:
            js_path.write_text("".join(lines), encoding="utf-8")
            print(f"  patched {js_path.name}")
    return total


def merge_auto_js_strings(zh: dict, en: dict) -> None:
    """Add remaining JS UI strings from auto-extraction under module.auto.* keys."""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from apply_i18n import translate_zh_to_en as zh_to_en  # noqa: WPS433
    from generate_i18n import _module_prefix, _slug, extract_js_strings  # noqa: WPS433

    counters: dict[str, int] = {}
    seen_values: set[str] = set()

    def in_catalog(val: str) -> bool:
        flat = flatten(zh)
        return val in flat.values()

    for js_path in sorted(JS_DIR.glob("*.js")):
        if js_path.name in ("i18n.js",):
            continue
        prefix = _module_prefix(js_path.name)
        for s in extract_js_strings(js_path.read_text(encoding="utf-8")):
            if in_catalog(s) or s in seen_values or len(s) < 2:
                continue
            if "window.t(" in s:
                continue
            if ".auto." in s or re.match(r"^[a-z][a-z0-9]*\.[a-z]", s):
                continue
            seen_values.add(s)
            base = _slug(s)
            counters[prefix] = counters.get(prefix, 0) + 1
            key = f"{prefix}.auto.{base}"
            n = 1
            while flatten(zh).get(key):
                n += 1
                key = f"{prefix}.auto.{base}_{n}"
            _set_nested(zh, key, s)
            _set_nested(en, key, zh_to_en(s))


def main() -> None:
    LOCALES.mkdir(parents=True, exist_ok=True)
    zh, en = build_locales()
    merge_auto_js_strings(zh, en)
    (LOCALES / "zh-CN.json").write_text(json.dumps(zh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (LOCALES / "en.json").write_text(json.dumps(en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote locales ({len(CATALOG)} catalog + auto keys)")
    patch_html()
    n = patch_js_whole_literals(flatten(zh))
    print(f"Patched JS: {n} whole-literal replacements")


if __name__ == "__main__":
    main()
