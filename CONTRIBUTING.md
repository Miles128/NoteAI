# 贡献指南

感谢你对 NoteAI 的关注！我们欢迎任何形式的贡献。

## 快速开始

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/<your-username>/NoteAI.git
cd NoteAI

# 2. 安装依赖
uv sync --extra dev --extra rag
npm ci

# 3. 启动开发环境
python run.py
```

## 开发规范

### 提交信息

采用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <description>

[optional body]
[optional footer(s)]
```

**类型**：
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式（不影响逻辑）
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建/工具

**示例**：
```
feat(rag): add citation source tracking
fix(workspace): resolve file watcher debounce issue
docs: update PRD with success metrics
```

### 代码规范

**Python**：
- 使用 `ruff` 格式化和检查
- 类型注解：必须
- 行长：120 字符
- 运行检查：`ruff check .` 和 `ruff format --check .`

**JavaScript**：
- 使用 ESLint（即将配置）
- 保持 IIFE 模块风格
- 全局状态通过 `window.AppState`

**Rust**：
- 使用 `cargo clippy` 检查
- 遵循 `rustfmt` 格式

### 分支策略

- `main`: 稳定版本
- `feat/*`: 新功能
- `fix/*`: 修复
- `refactor/*`: 重构

### Pull Request 流程

1. 从 `main` 创建分支
2. 提交变更
3. 确保 CI 通过
4. 创建 PR，填写模板
5. 等待 Review

## 报告问题

### Bug 报告

请使用 [Issue 模板](https://github.com/Miles128/NoteAI/issues/new?template=bug_report.md)，包含：

- 操作系统和版本
- NoteAI 版本
- 复现步骤
- 期望行为 vs 实际行为
- 日志（如有）

### 功能请求

请使用 [Feature Request 模板](https://github.com/Miles128/NoteAI/issues/new?template=feature_request.md)。

## 开发任务

查看 [Good First Issues](https://github.com/Miles128/NoteAI/labels/good%20first%20issue) 了解适合新手的任务。

## 许可证

贡献即表示你同意你的代码在 MIT 许可证下发布。

## 问题？

在 [Discussions](https://github.com/Miles128/NoteAI/discussions) 提问。
