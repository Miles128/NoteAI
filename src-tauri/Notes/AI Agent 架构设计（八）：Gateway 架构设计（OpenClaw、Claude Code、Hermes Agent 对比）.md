---
title: "AI Agent 架构设计（八）：Gateway 架构设计（OpenClaw、Claude Code、Hermes Agent 对比）"
tags: [AI Agent, 架构设计]
date: 2026-04-25
---

# AI Agent 架构设计（八）：Gateway 架构设计

> **目标**：理解三个框架如何设计 Agent 的入口和路由层，以及多渠道接入、身份认证、请求调度背后的工程取舍
> **适合**：对 Agent 底层设计感兴趣，想真正理解"为什么这样设计"的读者
> **预计阅读**：15 分钟

## Gateway：Agent 的前门

用户通过什么方式和 Agent 交互？微信、Slack、Telegram、Web 界面、API……每个渠道的请求格式不同、认证方式不同、消息类型不同。

**Gateway 就是 Agent 的前门。** 它负责接收所有渠道的请求，统一处理认证、路由、速率限制，然后把请求转给后端的 Agent 处理。

没有 Gateway，每个渠道都要自己实现一套接入逻辑，重复且容易出错。有了 Gateway，所有渠道走同一个入口，安全策略和路由规则集中管理。

但 Gateway 不只是"一个反向代理"。它涉及三个核心设计问题：

1. **多渠道怎么接入**——不同渠道的消息格式、交互模式、能力限制怎么统一
2. **多 Agent 怎么路由**——不同用户、不同场景怎么分配到不同的 Agent
3. **安全怎么保障**——认证、授权、速率限制怎么在入口层实现

三个框架对这三个问题的答案，揭示了三种完全不同的 Gateway 哲学。

## OpenClaw：Gateway 是核心，一切皆路由

### 架构：Gateway 是唯一的常驻进程

OpenClaw 的架构里，Gateway 是唯一的常驻进程。Agent 本身不是进程，是一组配置文件。当消息到达 Gateway，它读取对应 Agent 的配置，构建系统提示，调用语言模型，返回结果。

这意味着 Gateway 承担了比"路由"更多的职责：

- **请求接收**：监听所有渠道的消息
- **Agent 解析**：根据路由规则找到对应的 Agent 配置
- **系统提示构建**：动态组合 SOUL.md、MEMORY.md、Skills 等内容
- **模型调用**：将构建好的请求发送给语言模型
- **响应返回**：将模型输出格式化后发回原始渠道

### 多渠道接入：Bindings 机制

OpenClaw 通过 Bindings 配置渠道和 Agent 的映射关系：

```json
{
  "bindings": [
    {
      "channel": "telegram",
      "agentId": "work-agent",
      "allowedUsers": ["user1", "user2"]
    },
    {
      "channel": "web",
      "agentId": "public-agent"
    }
  ]
}
```

每个 Binding 可以指定：哪个渠道、路由到哪个 Agent、允许哪些用户访问。这提供了灵活的路由能力——同一个 Gateway 可以服务多个 Agent，不同用户看到不同的 Agent。

### 安全：Gateway 层的认证

OpenClaw 的认证在 Gateway 层实现：

- **API Key 认证**：每个渠道配置独立的 API Key
- **用户白名单**：限制特定用户访问特定 Agent
- **速率限制**：防止滥用

但默认配置下，很多安全选项是关闭的。2026 年初的安全扫描发现，超过 13.5 万个暴露在公网的 OpenClaw 实例中，63% 完全没有身份认证。这是"默认开放"哲学的代价。

## Claude Code：无 Gateway，直接交互

### 架构：CLI 优先，无中间层

Claude Code 没有传统意义上的 Gateway。它的主要交互方式是 CLI——用户在终端里直接运行 `claude`，Agent 在本地启动，直接和用户交互。

这种设计选择反映了 Claude Code 的定位：**个人开发者的本地工具，不是多用户的服务端应用。**

没有 Gateway 意味着：

- **没有路由问题**——只有一个用户，一个 Agent
- **没有多渠道问题**——只有 CLI 一个入口
- **没有认证问题**——本地运行，不需要身份验证

### MCP 作为扩展入口

虽然没有传统 Gateway，Claude Code 通过 MCP Server 接入外部能力。MCP 在某种程度上扮演了"能力网关"的角色——Agent 通过 MCP 协议发现和调用外部工具。

但 MCP 是工具层的协议，不是用户层的 Gateway。它解决的是"Agent 怎么访问外部能力"，不是"用户怎么访问 Agent"。

### API 模式：面向开发者的 Gateway

Claude Code 提供了 API 模式（`claude api`），允许开发者将 Claude Code 集成到自己的应用中。这个模式下，开发者需要自己实现 Gateway 层的认证、路由、速率限制。

这和 OpenClaw 的"内置 Gateway"形成对比。Claude Code 把 Gateway 的责任交给了使用者——如果你只是本地用，不需要 Gateway；如果你要做多用户服务，自己搭。

## Hermes Agent：多后端 Gateway，安全优先

### 架构：六种执行后端

Hermes Agent 的 Gateway 设计最灵活，支持六种执行后端：

1. **本地执行**：直接在本机运行
2. **Docker 后端**：在容器中隔离执行
3. **Modal 后端**：云端无服务器执行
4. **Daytona 后端**：开发环境即服务
5. **MCP 客户端**：作为 MCP 客户端接入其他 Agent
6. **MCP 服务器**：作为 MCP 服务器被其他工具调用

每种后端有不同的安全隔离级别和资源限制。用户可以根据任务的风险等级选择合适的后端。

### 安全：后端即安全边界

Hermes 的 Gateway 设计最独特的地方是：**后端本身就是安全边界。**

当运行在 Docker 后端时，容器提供了操作系统级的隔离——即使 Agent 被攻陷，损害被限制在容器内。当运行在 Modal 后端时，执行环境是临时的、无状态的——任务完成后环境销毁，没有持久化的攻击面。

这意味着 Hermes 不需要在 Gateway 层做复杂的安全检查，而是把安全责任下推到执行后端。**基础设施层的安全比应用层更可靠。**

### MCP 双向参与

Hermes 的 MCP 设计是双向的：

- **作为 MCP 客户端**：连接外部 MCP 服务器，使用其工具
- **作为 MCP 服务器**：通过 `hermes mcp serve` 把自己的会话历史和记忆暴露给其他工具

这让 Hermes 可以被 Claude Desktop、VS Code、Cursor 等工具通过 MCP 协议调用，成为更大工作流的一部分。

## 三种 Gateway 哲学的对比

| 维度 | OpenClaw | Claude Code | Hermes Agent |
|------|----------|-------------|-------------|
| Gateway 位置 | 核心组件 | 无（CLI 直连） | 多后端可选 |
| 多渠道支持 | 内置（Bindings） | 无 | 通过 MCP |
| 多用户支持 | 内置 | 无 | 通过后端隔离 |
| 安全模型 | Gateway 层认证 | 本地信任 | 后端即安全边界 |
| 灵活性 | 中等 | 最低 | 最高 |
| 部署复杂度 | 中等 | 最低 | 最高 |

## 选择建议

- **个人开发者、本地使用** → Claude Code 的无 Gateway 设计最简单，零配置
- **多渠道、多用户服务** → OpenClaw 的内置 Gateway 最完整，开箱即用
- **安全隔离、多环境执行** → Hermes 的多后端设计最灵活，按需选择

Gateway 的设计，本质上是在**简洁性**和**灵活性**之间做取舍。Claude Code 走极简路线——不需要就不做。OpenClaw 走全面路线——内置所有常用功能。Hermes 走可组合路线——提供多种后端，用户按需选择。

未来的趋势是**Gateway 即平台**——不只是路由和认证，还包括可观测性、审计日志、成本控制、A/B 测试等运维能力。三个框架都在朝这个方向演进，但目前只有 OpenClaw 具备了基本的平台能力。
