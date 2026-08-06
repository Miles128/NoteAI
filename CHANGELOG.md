# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式。

## [Unreleased]

### 新增
- 笔记合并建议：`get_note_merge_suggestions` RPC 基于 RAG 索引向量相似度 + 语义库实体/概念共享分析笔记合并候选，分级 A（同源）/B（深度重叠）/C（主题关联），只读分析、stale 过滤、索引未建立时优雅降级（`utils/note_merge_analyzer.py`）；`merge_suggested_notes` RPC 执行合并（复用 `merge_note_group` 的 LLM 整合 + send2trash 删除 + `.links.json` 链接重定向），打通「建议→执行」闭环
- 首启示例库：空工作区一键创建「普通人的AI指南」示例工作区（`create_sample_workspace` RPC）
- Release 工作流 `release.yml`：打包前端 bundle、自包含 sidecar Python 与 Tauri dmg，tag 推送自动发布 Release
- 知识变化摘要：语义编译自动记录命题/实体/概念/文档的新增、更新与失效，语义工作台概览展示最近 7 天变化（`get_semantic_changes` RPC）
- 首页知识动态卡片：首页展示最近 7 天语义变化（命题/实体/概念新增、更新与失效）
- 一键周报：首页生成知识库周报（`generate_weekly_brief` RPC），LLM 生成或结构化降级，可保存为笔记
- RAG 无证据显式声明：检索无结果时改用专用提示词，明确告知用户知识库中无直接证据，不再空上下文自由发挥
- 新建笔记触发交叉引用发现：`create_note_from_draft` 保存后轻量启发式扫描关联笔记；编辑保存的交叉引用改为轻量路径（不再每次消耗 LLM）
- Claim 抽取黄金评测集：锁定 Claim 类型门禁、逐字证据校验与证据可解析性，回归即失败
- 贡献指南 (CONTRIBUTING.md)
- 安全策略 (SECURITY.md)
- Issue 模板和 PR 模板
- CI/CD 完善：添加 Python lint、type check

### 变更
- 综述写作规则硬化：`TOPIC_SURVEY_PROMPT` 与 `CASCADE_SURVEY_NEW/UPDATE_PROMPT` 重写——综述定位改为「简略概括而非复述」（1-3 句讲清核心结论、禁止完整代码/长表格/逐步操作、篇幅为原文 20%-40%、深度内容用「详见：文件名.md」替代），消除原「全面性/篇幅匹配」导致的综述复述问题
- 黄金评测集扩充至 105 例：新增属性/定义/指令类拒收与 `reduces` 等英文判断门禁；修复「检索增强生成」定义泄漏与 `reduces` 误拒；`CLAIM_POLICY_VERSION` 5→6
- 链接治理（`.links.json`）：保存时交叉引用只保留真实引用（正文/摘要提及标题），移除「共享标签/语义相关/邻居/同主题」四路对称弱启发式（此前导致 92% 链接双向爆炸、反向链接面板充满无关内容）；新增 `purge_weak_links` RPC 清洗历史弱链接，新增 `backfill_semantic_bidirectional` RPC 对「共享 ≥6 个实体/概念」的文档对补双向链接（用户工作区 16236 → 1253 条，删除 15585 条弱链接 + 回填 602 条语义双向）
- `scripts/bundle_sidecar_python.sh` 产出自包含 sidecar Python（合并标准库与实体解释器，修复 venv 符号链接在应用包内断裂）

### 移除
- 死 RPC 与死代码：`append_chat_to_survey`、`get_survey_status`、`get_topic_tree_3tier`、`rag_retrieval_debug`、`start_semantic_claims_compile`、`retry_semantic_failed_blocks`、`set_abstract_config`（含 `survey_append.py` 模块与 `SURVEY_CHAT_APPEND_PROMPT`）

### 变更
- 文档清理：合并 CLAUDE.md → AGENTS.md，合并 简介.md → README.md，删除过时的 docs/API.md、docs/USAGE.md、docs/README.md 及旧设计文档
- 更新 CI 配置以支持更多检查

## [0.1.0] - 2024-XX-XX

### 新增
- 初始版本发布
- 三级主题系统
- RAG 检索与对话
- 双向链接
- 知识图谱可视化
- 网页下载与格式转换
- 云盘同步（实验性）

[Unreleased]: https://github.com/Miles128/NoteAI/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Miles128/NoteAI/releases/tag/v0.1.0
