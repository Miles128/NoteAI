# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式。

## [Unreleased]

### 新增
- 重叠笔记合并：`scan_merge_candidates` RPC 按预设（严格/均衡/宽松）与可覆盖阈值扫描合并候选，`merge_note_group` RPC 执行合并（LLM 整合 + send2trash 删除 + `.links.json` 链接重定向）
- Release 工作流 `release.yml`：打包前端 bundle、自包含 sidecar Python 与 Tauri dmg，tag 推送自动发布 Release
- 知识变化摘要：语义编译自动记录实体/概念/文档的新增、更新与失效，语义工作台概览展示最近 7 天变化（`get_semantic_changes` RPC）
- 首页知识动态卡片：首页展示最近 7 天语义变化（实体/概念新增、更新与失效）
- 一键周报：首页生成知识库周报（`generate_weekly_brief` RPC），LLM 生成或结构化降级，可保存为笔记
- RAG 无证据显式声明：检索无结果时改用专用提示词，明确告知用户知识库中无直接证据，不再空上下文自由发挥
- 新建笔记触发交叉引用发现：`create_note_from_draft` 保存后轻量启发式扫描关联笔记；编辑保存的交叉引用改为轻量路径（不再每次消耗 LLM）
- Claim 抽取黄金评测集：锁定 Claim 类型门禁、逐字证据校验与证据可解析性，回归即失败
- 贡献指南 (CONTRIBUTING.md)
- 安全策略 (SECURITY.md)
- Issue 模板和 PR 模板
- CI/CD 完善：添加 Python lint、type check

### 变更
- 综述写作规则硬化：`CASCADE_SURVEY_NEW/UPDATE_PROMPT` 重写——综述定位改为「简略概括而非复述」（1-3 句讲清核心结论、禁止完整代码/长表格/逐步操作、篇幅为原文 10%-30%、深度内容用「详见：文件名.md」替代），消除原「全面性/篇幅匹配」导致的综述复述问题
- 黄金评测集扩充至 105 例：新增属性/定义/指令类拒收与 `reduces` 等英文判断门禁；修复「检索增强生成」定义泄漏与 `reduces` 误拒；`CLAIM_POLICY_VERSION` 5→6
- 链接治理（`.links.json`）：保存时交叉引用只保留真实引用（正文/摘要提及标题），移除「共享标签/语义相关/邻居/同主题」四路对称弱启发式（此前导致 92% 链接双向爆炸、反向链接面板充满无关内容）；新增 `purge_weak_links` RPC 清洗历史弱链接，新增 `backfill_semantic_bidirectional` RPC 对「共享 ≥6 个实体/概念」的文档对补双向链接（用户工作区 16236 → 1253 条，删除 15585 条弱链接 + 回填 602 条语义双向）
- `scripts/bundle_sidecar_python.sh` 产出自包含 sidecar Python（合并标准库与实体解释器，修复 venv 符号链接在应用包内断裂）
- CSS 死样式清理：按「类名在 index.html / 全部 TS 源码 / 签入 bundle / dist 产物 / 懒加载 `webui/lib/tiptap-bundle.js` 中零出现」判死，删除 391 条规则（10616 → 8392 行）；拼接类（`tree-level-*`、`graph-legend-dot-*`）与 ProseMirror 注入类经回溯保留，判据无类名的选择器一律视为活
- 组织规则模态框提示文案对齐样式：`webui/index.html` 两处 `class="hint"`（周报模态框描述、组织规则主题列表提示）改为 `settings-hint`。全库 CSS 从未有过裸 `.hint` 规则（只有 `.schema-wizard-step .hint`，而其祖先 DOM 已下线），这两处提示此前完全没有样式；设置面板里的同文案本来就用 `settings-hint`，此处只是让模态框跟上，未新增任何规则
- `webui/css/schema-wizard.css` 下线：多步向导 DOM 已不存在，把仍在使用的 10 条规则（`.schema-option-*`、`.schema-l1-tag(s)`、`.schema-wizard-footer`）迁到 `webui/css/components.css`，丢弃 6 条零引用规则（`#schema-wizard-modal` 4 条、`#schema-wizard-preview`、`.schema-wizard-progress`），并移除 `index.html` 的 stylesheet link。迁移前确认这些类名在其他 CSS 中无定义，故层叠顺序不受影响
- 修复过又被判定为死的 `.schema-wizard-progress`：`387af5a` 重构时吃掉了它的选择器行，留下 3 条孤立声明和一个多余 `}`（致该文件括号 26/27 长期失衡）；补回后查明该元素在模态框里已不存在，遂连同整文件一并下线，现 11 个 CSS 文件全部平衡
- 设置项「改了不生效」修复：纸质主题补入 `theme_preference` 白名单（此前点选即时生效但重启回滚）；`merge_preset` / `merge_overrides` 成为 `AppConfig` 字段并在 `_save_ui_config`/`_get_ui_config` 往返（此前 18 个保存分支里没有它们，三档单选与 8 个阈值框每次重开都回默认）；合并高级阈值的 DOM id 按下划线↔连字符映射修正（重叠度/主题名/主题内容 3 个框此前完全绑不上）；`saveAssistantUiConfig` 改走 `window.state.saveUiConfig` 门面以同步 uiConfig 缓存
- 搜索接通主题/标签筛选：`searchFiles` 转发 `topic`/`tag`（此前只发 `query`，界面上两个筛选框是死输入框，而后端 `intel_handler` 的过滤分支一直存在）
- RAG 预设不再静默回落：`_readRagPresetFromForm` 对已移除输入框的 `rag_hyde_threshold`/`rag_rerank_skip_score` 改读已保存值（此前动一下稠密权重/Top-K 滑块就会把「深度」档写回 0.33/0.75）
- 新笔记自动归类补开关：设置面板新增「新笔记自动归入主题」，`auto_topic` 保存走 `_coerce_bool`（此前只有 `autoSaveConfig` 把值硬写成 `true` 且无人调用）；预览字体补下拉控件，接上早已存在的 `applyContentFonts` 生效路径
- 链接治理两个操作补成真实 RPC：`purge_weak_links` / `backfill_semantic_bidirectional` 注册到 `links_handler` + Rust 白名单 + `api.ts`，并纳入 `DESTRUCTIVE_METHODS` 限流（此前只是被单测调用的 Python 函数，AGENTS.md 却记载为已在白名单）
- 待确认页补「全部重试综述」按钮，接上后端一直完整的 `retry_all_cascade_failures`

### 移除
- D1 功能裁撤：标签/关系侧栏视图（tags.ts、integrator.ts、tab-1 整合页、sidebar-tags/graph 面板与 dock）、主题提取链（`extract_topics` RPC + `topic_extractor.py` + `topic_extraction.yaml`），并清理对应 locales（`integrator`/`tags`/`sidebar.tag*`/`common.tagsCount|linksCount`）与 CSS 孤儿（`sidebar-tag*`、`link-card*`、`progress-container`）；7 个 tags RPC 保留为 backend-only（`KNOWN_BACKEND_ONLY_METHODS`）
- 功能裁撤：RSS 订阅与手动拉取、云盘同步残余、笔记批量整合（note_integration RPC）、文件格式转换 RPC（start_file_conversion）、主题 AI 子树（ai_topic_analyze / ai_topic_survey / apply_topic_suggestion / batch_auto_assign_topics / rename_topic / move_file_to_topic）、综述遗留 RPC（get_survey_overview / toggle_survey / sync_wiki_with_files）及对应前端死路径（converter.ts、日志面板、pending 续跑按钮等）
- 死 RPC 与死代码：`append_chat_to_survey`、`get_survey_status`、`get_topic_tree_3tier`、`rag_retrieval_debug`、`start_semantic_claims_compile`、`retry_semantic_failed_blocks`、`set_abstract_config`（含 `survey_append.py` 模块与 `SURVEY_CHAT_APPEND_PROMPT`）
- 仓库垃圾清理：根目录 `tmp_rebuild_rag.log`、空目录 `Projects/`、`NoteAI.egg-info/`；`.gitignore` 补 `*.egg-info/` 与 `src-tauri/resources/`（打包暂存产物）
- 标签管理台后端下线：`tags_handler.py`（301 行）删除，7 个 tags RPC 连同 Rust 白名单与 `KNOWN_BACKEND_ONLY_METHODS` 豁免一并移除（豁免清单清空为 `set()`），`TestTagsHandler` 契约测试同步删除。标签作为笔记属性保留：`utils/tag_extractor.py` 仍在导入/下载时按文件名产出标签并写 `tags.md`，检查器属性页与图谱标签节点、搜索的标签筛选均不受影响
- 零调用前端与资产：`topic.ts` 全套（主题待确认浮层，渲染函数与 `TreeModule.hasTopicPending` 均无消费者）、`index.html` 的 `topic-pending-panel` 容器及其 CSS、`api.ts` 窗口控制四封装（`moveWindow`/`minimizeWindow`/`maximizeWindow`/`closeWindow`，拖动与窗口边框本就由 Tauri 承担）、`autoSaveConfig`
- 重复与过期触发：`fix_survey_topics` RPC（实现只是再跑一次 `sync_wiki_with_files`，sidecar 启动与文件监听防抖已各同步一次，且名字与实现不符）
- 首启示例库残骸：`python/sidecar/sample_workspace/`（216K / 10 篇 md）与 `pyproject.toml` 的 package-data 声明——代码链已于 2026-09-20 删除，数据与打包声明一直没跟上，CHANGELOG 也还在宣传
- 零引用资产：`version.txt`（消费者 `sync_version.py` 已删）、`start.sh`（依赖清单含非项目依赖 `FlagEmbedding`）、`tests/test-modules.html`（引用早已不存在的 `./js/converter.js` 等）、`WorkspaceStateManager._try_read_backup`
- locales 孤儿文案：en/zh-CN 各删 159 个叶子键（1134 → 975，占 14%），主要为命题层（claim/verify/verdict/evidence/conflict）、D1 主题子树、未接线的综述简报面板与已删控件标签；口径为「拼接感知」——`graph.param.*`、`assistant.citationQuality.*` 等由字符串拼接取键的命名空间一律保留

### 变更
- 文档清理：合并 CLAUDE.md → AGENTS.md，合并 简介.md → README.md，删除过时的 docs/API.md、docs/USAGE.md、docs/README.md 及旧设计文档
- 更新 CI 配置以支持更多检查
- AGENTS.md 前端架构描述修正：TS 源码 + esbuild 打包（此前仍写 vanilla JS 无 bundler）；inspector 描述移除已删除的命题层

## [0.1.0] - 2024-XX-XX

### 新增
- 初始版本发布
- 三级主题系统
- RAG 检索与对话
- 双向链接
- 知识图谱可视化
- 网页下载与格式转换

[Unreleased]: https://github.com/Miles128/NoteAI/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Miles128/NoteAI/releases/tag/v0.1.0
