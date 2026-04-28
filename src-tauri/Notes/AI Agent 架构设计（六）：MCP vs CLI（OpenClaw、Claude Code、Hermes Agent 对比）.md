---
title: "AI Agent 架构设计（六）：MCP vs CLI（OpenClaw、Claude Code、Hermes Agent 对比）"
tags: [AI Agent, MCP, 架构设计]
date: 2026-04-25
---

# AI Agent 架构设计（六）：MCP vs CLI

2026 年，AI Agent 圈有一个争论越来越热：

**到底该用 MCP 还是 CLI？**

Perplexity 的 CTO 在公开场合说公司内部正在降低 MCP 的优先级。YC CEO Garry Tan 说 MCP 吃掉太多上下文窗口，认证机制也有问题，他自己用 30 分钟造了个 CLI 替代品。Hacker News 上反 MCP 的声音越来越多。

与此同时，OpenClaw 创始人 Peter Steinberger 在 X 上说了一句话，被广泛转发："当 Agent 能直接跑命令行，为什么还要多一层协议？"——然后他造了 MCPorter，一个把 MCP 服务器转换成 CLI 工具的工具。

这个争论不是在争谁更高级，而是触碰了一个真实的架构问题。

## MCP 是什么，CLI 是什么

**CLI（命令行工具）**：`git status`、`gh pr list`、`docker ps`——Agent 直接在终端里跑这些命令，拿到输出，继续干活。

模型在训练数据里见过海量的命令行操作，知道怎么用这些工具。零额外配置，直接可用。

**MCP（Model Context Protocol）**：Anthropic 制定的开放标准，定义了 Agent 和外部工具之间通信的统一格式。工具方（数据库、GitHub、Slack……）把自己的能力包装成 MCP 服务器，Agent 通过 `tools/list` 发现有哪些工具，通过 `tools/call` 调用它们。

相当于给所有工具装了一个统一的插头——理论上，任何遵循 MCP 标准的工具，都能接进任何支持 MCP 的 Agent。

## 为什么这个争论会出现：一个真实的 Token 问题

Scalekit 做了一组基准测试，结果很直接：

**完成同一个 GitHub 任务：**

**为什么差这么多？**

GitHub 的 MCP 服务器暴露了 43 个工具。Agent 连上它之后，这 43 个工具的完整 schema——名称、参数、描述、用法——全部注入上下文。不管 Agent 用不用这些工具，schema 都在那里占着空间。

对一个简单的"查一下这个 PR 的状态"任务，Agent 实际只用了 1-2 个工具，但要带着另外 41 个工具的 schema 全程陪跑。

用 CLI 的话，Agent 直接跑 `gh pr view 123 --json title,state`，几百个 Token 搞定，连发现工具的步骤都省了——因为模型训练时就见过这个命令，直接知道怎么用。

**这就是 MCP 的 Token 税。**

连接的服务器越多，税越重。有人测过接 4 个 MCP 服务器（GitHub、数据库、Microsoft Graph、Jira），光工具 schema 就用掉 150,000+ Token——上下文窗口还没开始干活就去了一大半。

## 那 MCP 没用了？不对

这个结论跳得太快。CLI 赢了个人开发者场景，但输了另一个场景。

**CLI 的根本限制：你的凭证，你的权限。**

Agent 跑 CLI，用的是你本地配置好的身份——你的 GitHub Token、你的 AWS 凭证、你的数据库密码。这对你自己的工作流完全没问题。

但如果你在做一个产品，你的用户要通过你的 Agent 访问他们自己的 GitHub、他们自己的 Salesforce、他们自己的工作区——这就不是"用我的凭证跑 CLI"能解决的了。

你需要：

这些东西，MCP 天然支持，CLI 做不到。

**还有另一个场景：没有 CLI 的系统。**

Salesforce 没有 CLI。Workday 没有 CLI。Greenhouse 没有 CLI。这些 SaaS 系统只有 API，而且通常还是需要 OAuth 的复杂 API。MCP 是为这种场景生的，CLI 根本进不了门。

## 结论：不是选边，是按场景分工

业界在这个争论里形成的共识，比"谁赢了"更有意思：

**CLI 适合的场景：**

- 模型训练数据里见过这个工具（`git`、`gh`、`aws`、`docker`……）
- 


- 


- 循环处理大批量数据（150 个 API 请求，CLI 可以写 for 循环，MCP 要调 150 次工具）

**MCP 适合的场景：**

- SaaS 系统（Salesforce、Workday，根本没有 CLI）
- 


- 


- 工具发现——不知道有什么可用时，MCP 能自动告诉 Agent

**最聪明的架构：同时用两个，按任务选择。**

Claude Code 就是这样做的——本地文件操作和代码执行走 CLI，SaaS 集成走 MCP，用 Skills 这一层把两者统一封装，Agent 不需要关心下面走的是哪条路。

## 三个框架各自怎么站队

### OpenClaw：MCP 作为生态继承层

OpenClaw 接 MCP 的出发点很直接：**外面已经有 5,800+ 个 MCP 服务器，不用自己造轮子。**

配置就是在 `openclaw.json` 里加一段 `mcpServers`，连上哪个服务器，Agent 就能用哪个服务器的工具。GitHub、Postgres、Slack、Notion——统统可以接。

但 OpenClaw 没有做工具的按需加载优化。接的服务器越多，上下文里的工具 schema 就越多，Token 消耗线性增长。社区实践发现，接超过 5-6 个 MCP 服务器后，上下文压力就开始变得明显。

对 CLI 的支持，OpenClaw 主要通过 Skills 系统——用 Skill 封装命令行操作，Agent 调用 Skill，Skill 去跑命令。这条路已经跑通，但没有形成 MCP 那样统一的发现和接入机制。

**总结：MCP 是 OpenClaw 的主要扩展路径，CLI 是补充。生态规模是最大优势，Token 效率是短板。**

### Claude Code：两条路都走，Skills 统一封装

Claude Code 对这个问题给出了最系统的架构答案。

**CLI 是默认执行方式。** Claude Code 本质上是一个能跑终端命令的 Agent，文件操作、代码执行、Git 操作——全部走 Shell。这是最轻量、最高效的路径。

**MCP 是结构化扩展层。** 接入 MCP 服务器时，Claude Code 做了一个关键优化：**延迟加载（**`defer_loading: true`**）**——Session 启动时只加载工具名称，完整 schema 只在真正需要时才加载。这把 MCP 的 Token 税从"全量预付"变成了"按需支付"。

同时有 tool search 机制——Agent 通过语义搜索找到相关工具，而不是遍历整个工具列表。

**Skills 是统一接口层。** 不管下面走的是 CLI 还是 MCP，对 Agent 来说都是调用一个 Skill。这个抽象让 Agent 不需要关心传输细节，也让同一个任务可以灵活地在两种路径之间切换。

从源码泄露里还能看到：Claude Code 的内置工具（文件读写、Shell 执行）和 MCP 工具，走的是同一套工具注册表——统一的权限门控、统一的 schema 验证，没有内外之分。Computer Use 功能本身也是作为 `@ant/computer-use-mcp` 实现的——Anthropic 没有为它写专用管道，而是用 MCP 服务器的标准接口实现。

**总结：CLI 干活，MCP 扩展，Skills 统一，三层分工最清晰。**

### Hermes Agent：MCP 客户端 + MCP 服务器，双向参与

Hermes Agent 对 MCP 的处理有一个独特的角度：**它不只是 MCP 客户端，自己也能作为 MCP 服务器。**

`hermes mcp serve` 命令让 Hermes 把自己的会话历史和记忆暴露给 MCP 客户端——Claude Desktop、VS Code、Cursor 可以通过 MCP 协议查询 Hermes 的历史记录。这让 Hermes 的记忆不只是给自己用，也可以被其他 AI 工具调用。

Hermes 还有 ACP（Agent Communication Protocol），专门用于和编辑器的双向通信——编辑器把当前打开的文件和光标位置告诉 Hermes，Hermes 据此更准确地理解任务上下文。

安全处理上，Hermes 对 MCP 子进程做了环境变量隔离——主机上的敏感凭证默认不传入 MCP 服务器进程，需要某个环境变量的服务器必须在 Skill 里显式声明。

CLI 方面，Hermes 通过六种执行后端支持本地和远程的命令行执行，但没有形成 MCP 那样的统一发现接口。

**总结：MCP 双向参与是最大特色，安全处理最保守，CLI 是执行选项之一但不是核心路径。**

## 这个争论的真正答案

MCP vs CLI 不是非此即彼的选择，是**按场景分工的问题**。

一句话总结行业共识：

> **CLI 处理模型已经知道的工具，MCP 处理需要发现和认证的工具。**

对个人开发者的工作流，CLI 更快更便宜。对面向用户的产品，MCP 解决了 CLI 解决不了的多用户认证问题。对没有 CLI 的 SaaS 系统，MCP 是唯一选项。

最成熟的 Agent 架构——比如 Claude Code——已经内部解决了这个问题：CLI 和 MCP 并行运行，Skills 这一层做统一封装，Agent 不用操心下面走的是哪条路。

这个问题社区还在热烈讨论，但架构答案其实已经在产品里了。