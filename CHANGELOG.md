# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式。

## [Unreleased]

### 新增
- 首启示例库：空工作区一键创建「普通人的AI指南」示例工作区（`create_sample_workspace` RPC）
- Release 工作流 `release.yml`：打包前端 bundle、自包含 sidecar Python 与 Tauri dmg，tag 推送自动发布 Release
- 知识变化摘要：语义编译自动记录命题/实体/概念/文档的新增、更新与失效，语义工作台概览展示最近 7 天变化（`get_semantic_changes` RPC）
- Claim 抽取黄金评测集：锁定 Claim 类型门禁、逐字证据校验与证据可解析性，回归即失败
- 贡献指南 (CONTRIBUTING.md)
- 安全策略 (SECURITY.md)
- Issue 模板和 PR 模板
- CI/CD 完善：添加 Python lint、type check

### 变更
- 黄金评测集扩充至 105 例：新增属性/定义/指令类拒收与 `reduces` 等英文判断门禁；修复「检索增强生成」定义泄漏与 `reduces` 误拒；`CLAIM_POLICY_VERSION` 5→6
- `scripts/bundle_sidecar_python.sh` 产出自包含 sidecar Python（合并标准库与实体解释器，修复 venv 符号链接在应用包内断裂）

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
