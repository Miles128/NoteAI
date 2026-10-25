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
- Rust 编译产物瘦身：`src-tauri/target/` 是一份 3.1 GB / 10,969 文件的**陈旧目录**——本机 `~/.cargo/config.toml` 早已把 `build.target-dir` 指向 `~/.cargo/target`（多项目共享），这个目录自迁移后不再被 cargo 使用，已用 `cargo clean` 删除。同时从 `crate-type` 去掉仅移动端需要的 `staticlib`（debug 下会多出数百 MB），dev profile 统一为 `debug="line-tables-only"` + `strip="debuginfo"` + 依赖 `opt-level=1` 且不带调试信息，并把这份配置从 `~/.cargo` 的个人设置落进仓库的 `src-tauri/.cargo/config.toml`，换机器与 CI 行为一致。实测当前有效产物 941 MB / 3,176 文件（deps 730 MB），我方 crate 的 rlib 101 MB→37 MB、不再生成 `.a`；全量重编 45 秒
- 知识库体检不再有两行假结果：`rag` 只查向量索引、BM25 缺失也报「正常」（`bm25_index_ready` 的结果算了但没进 detail），`fulltext` 直接硬编码 `{"ok": True}`——全文索引在内存里、不建就永远不知道覆盖了多少。现在 RAG 分三种文案（索引缺失 / 向量与 BM25 均正常 / BM25 缺失但查询时自动重建），全文索引真建一次并报实测条数（用户工作区 224 篇、9.2 万词条）；`semantic` 把早已算出的编译覆盖率写进 detail（192/194 篇时明确提示「有笔记未编译」）
- 删除 `.links.json` 的 `last_scan` 死字段：全仓 `webui/js/` 零引用，写入方 `discover.py` 两处、读取方 `persist.py` 两处与语义工作台链接分页一并清掉，索引文件回到只有 `links` 一个键
- 下线 `get_activity_log` RPC（api.ts + Rust 白名单 + Python 路由三层同步，前端方法数 109→108）：删除设置页「操作记录」Tab 后已无任何前端调用方。连带删除 `utils/activity_log.py` 整个兼容壳——`add_entry` 只是 `append_log` 的别名，`get_entries` 是给已删 UI 整形的读取器，`clear_log` 零调用；两个写入方（`topic/assigner.py`、`topic_placement.py`）改为直接调 `append_log`，与 `cascade.py`/`kb_lint.py` 一致
- 打包瘦身：`bundle.resources` 的 glob 收 `python/` 全部文件且 Tauri 不支持取反，`__pycache__`（2.2 MB，占该目录 69%）与 `.DS_Store` 一直被打进 app 包——新增 `scripts/clean-python-artifacts.mjs`（`npm run clean:pycache`）挂在 `beforeBuildCommand` 最前，`python/` 3.2 MB→1.0 MB；`bundle_sidecar_python.sh` 复制 venv 后同样剔除字节码缓存。删除零引用的依赖：`cryptography`（24 MB，连带 `cffi`/`pycparser`；凭据自 2026-09-20 起明文存放，Fernet 路径已删）与 npm 的 `punycode`（全仓无一处 import）
- 修复首启向导点遮罩后界面半加载：`workspace-rules.ts` 的遮罩关闭只隐藏 DOM、不结束 `openSetupModal()` 的 Promise，而启动链 `app.ts:60 → checkWorkspaceStatus → maybePromptSetup` 正在 await 它，于是文件树加载、首页刷新与启动入库全部不执行。关闭改走 `resolve(false)` 并透传给调用方，未配置时照常继续 `runPostWorkspaceSetup()`
- 删除设置页「操作记录」Tab：全仓无一处 JS 读取 `#settings-activity-log`，切进去永远停在「加载中…」；同时删除待确认页的活动日志分支（取的 `#pending-view-log` 元素不存在，每次加载白发一次 `get_activity_log` 再整段丢弃）。连带清理导航按钮、4 条 CSS 规则与 5 个 locale key。`wiki/log.md` 仍照常写入，`parse_log_entries` 的库内读取方（级联、Lint）不受影响
- 首页「知识动态 · 查看全部」改跳 `objects`：原先跳 `overview`，而 `semantic.categories` 没有这个键，点进去标题直接显示原始 key、列表恒空
- 语义工作台可见类别改为只认侧栏真实存在的 `data-category`：设置里的「主题简报」勾选没有对应入口（勾了无效），且只留它一项还能通过「至少保留一个」校验、把三个入口全部隐藏，工作台从此进不去。删掉该勾选，并过滤历史 localStorage 中残留的 `brief` 值
- AGENTS.md 删除对 `embedder.py` 中 `lexical_weights` 的描述：全仓 `lexical` 只命中 AGENTS.md 自己，该机制早已整体删除，按文档排查会白找一轮
- 二轮审计清理：删除零调用死代码——`rag/retriever.py:incremental_update`（与 `ingest_index.py:replace_file_chunks` 重叠的旧单文件索引路径，全仓无调用者）、`_link_discovery_lock` 空锁（声明并代理到 `BaseHandler`，从未被 `with` 使用）、无读取方的 window 挂载（`showAbout`/`onConfirmLink`/`onRejectLink`/`onAddTopicFromFileTree`/`onAddNoteFromFileTree`/`graphSetLayoutMode`/`toggleSemanticWorkbench`/`SchemaWizard`/`loadLazyCss`/`checkIsTauri`/`getTauriInvoke`）与 `main.mjs` 的 `IconsModule`/`SearchModule` 自我赋值；AGENTS.md 线程安全条目按实际锁清单更正（`_cache_lock`、`_rag_chat_lock` 均不存在）
- 下线链接治理双件套 `purge_weak_links` / `backfill_semantic_bidirectional`（Python 路由 + Rust 白名单与 `DESTRUCTIVE_METHODS` + `api.ts` 封装 + 单测）：对用户工作区实测，前者只补「两侧都零边」的文档对且一产出就是双份 pending，后者只对已绝迹的弱启发式 reason 生效、对真实库空转
- 语义抽取 confidence 标定：`semantic_extract.yaml` 两处 JSON 示例值从 `0.0` 改为 `0.9` 并写明取值规则（此前模型照抄示例的 0.0，被工作台 standard 档 `≥0.5` 全部过滤，表现为「编译跑了但工作台空着」）；`PROMPT_VERSION` 10→11，已编译的语义库需重跑全量语义编译才享受新标定
- 「召回 Top-K」改名「召回候选深度」并收到真实生效区间 4-8（候选数 = `top_k × 3` 且被夹在 [12, 24]，此前 1-50 的滑块几乎无感）；补提示说明最终引用条数由问题类型自动决定、上限 8；后端 `rag_top_k` 读写两侧同步夹紧
- 全文搜索改为中文可用：`utils/fulltext_index.py` 原先把连续汉字切成一个 token 并只做精确匹配，搜「笔记」命中不了「我的笔记系统」；现按相邻二字组合（bigram）入索引，查询侧同切并要求同组全部命中（等价子串包含），组间改 AND 计分。实测用户工作区 224 篇笔记：建索引 0.5s、单次查询 0.3ms、词条 9.2 万；「笔记」命中 46 篇、「反向传播」17 篇、「A2A」10 篇
- 综述页退出链接图：新增 `utils/links/persist.py:_is_survey_note`（文件名以「综述」结尾 **或** frontmatter `type: survey`，任一命中即算），链接发现的两个入口按来源侧提前返回、候选池按目标侧过滤，与 README 同级处理；综述页是聚合视图，什么都提一点，过去只贡献高共享数的虚关联。用户工作区实测：判据命中 2 篇（1 篇级联生成落在 Notes/、1 篇手写章节综述），一次性删除相关边 99 条（86 待确认 + 13 已确认，按用户指令不分状态全删），链接索引 897→798、待确认 531→445，备份 `.links.json.pre-survey-exclude-2026-09-26`；wiki/ 下 4 篇主题综述本就被目录跳过，不参与
- 链接建议不再重灌低置信 pending：`_SEMANTIC_SHARE_MIN` 3→6（3~5 档曾占待确认积压的 65%），强/中两档改判为 ≥8/≥6；同时删除从未挂上链路的 `_vector_search_candidates`（"语义相关"）与 `_one_hop_neighbors`（"已确认链接的邻居"）两个弱启发式生成器
- LLM 客户端按 (api_key, base_url) 复用：`_ChatClient` 此前每次调用新建 OpenAI SDK 实例（重建 httpx 连接池、多付一次 TCP+TLS 握手约 100-300ms），一次导入发 6+ 次调用就握手 6+ 次
- 语义抽取的源文件变更校验按 (mtime_ns, size) 记忆整篇哈希：原来每个 block 落库前都重读并哈希一次全文（50 块文档＝50 次全文件读），现在文件未变则只读一次，判定逻辑不变
- `sync_wiki_with_files` 不再把每篇笔记读两遍（frontmatter 解析与主题回写共用同一次读取）
- `_rag_index_status` 改走按 stat 键缓存的 manifest 读取（此前直读磁盘重建 dict，onboarding 期间每 5s 一轮）
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
- 修复流式 LLM 调用把有效并发砍半：`call_llm_raw_stream` 的槽位在 `_retry_with_backoff` 与 `_run_stream_with_timeout` 各取一次，而 `threading.Semaphore` 不可重入，于是**一次流式调用占掉 4 个槽位里的 2 个**。后果是第 3 个并发调用者在 `acquire(timeout=60)` 等满后直接吃到「LLM 调用并发已满」的硬错误，且该文案不匹配 `_RETRYABLE_KEYWORDS`、不会退避重试；一次全量语义编译的 `ThreadPoolExecutor(max_workers=4)` 与 RAG 对话争抢同一批槽位就能把对话挤爆。现在槽位由 `_retry_with_backoff` 单点持有、内层传 `slot_held=True` 复用，有效并发恢复为 4
- 流式调用超时不再永久泄漏并发槽位：`stop` 事件只在 chunk 之间检查，provider TCP 层挂死时后台线程永不退出，槽位随其 `finally` 被永久占住，累计 4 次即让整个进程的 AI 功能失效（且不像 reranker 有 60s 冷却兜底）。改为超时分支在调用线程侧兜底归还，新增 `_LLMSlot` 保证「谁归还、归还几次」收敛到一次，旧线程随后退出时其 `finally` 归还被去重
- 用户可见写路径补齐原子写：全仓 49 处 `.write_text(` 里只有 13 处走 `atomic_write_text`——WIKI.md 的 7 处 CRUD（`utils/wiki/crud.py`，AI 编译的知识层，崩溃即半截）、标签 frontmatter 回写（`tag_extractor` 2 处）、编译后的笔记正文（`note_compiler`）、主题移动/清空/格式优化（`topic/file_ops` 3 处）、笔记合并稿（`duplicate_review` 2 处）、用户 `schema.md` 与 `.ai_memory/project_rules.md`（`schema_manager` 4 处）、设置与 API 配置 JSON（`app_config` 3 处）全是裸写。`atomic_write_text` 同步补上权限位继承：目标已存在时沿用原权限（`mkstemp` 默认 0600，直接 `os.replace` 会把原本 0644 的用户笔记悄悄改成 0600），新文件仍为 0600

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
