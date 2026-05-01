---
title: "AI Agent 架构设计（四）：多 Agent 协作（OpenClaw、Claude Code、Hermes Agent 对比）"
tags: [AI Agent, 架构设计]
date: 2026-04-25
---

# AI Agent 架构设计（四）：多 Agent 协作

**目标**：从架构层面理解三个框架如何设计多 Agent 协作，以及角色分离、上下文隔离、通信协调背后的工程取舍
**适合**：对 Agent 底层设计感兴趣，想真正理解"为什么这样设计"的读者
**预计阅读**：15 分钟

## 为什么需要多 Agent？

单个 Agent 有两个根本限制。

**第一，上下文窗口是有限的。** 一个复杂项目涉及的文件、历史、工具调用结果，很快就会撑满单个上下文窗口。窗口越满，模型注意力越分散，"Lost in the Middle"问题越严重，输出质量下降。

**第二，一个 Agent 同时只能做一件事。** 如果一个任务有四个相互独立的子任务，单 Agent 必须串行——研究完再写，写完再审查，审查完再测试。四个子任务各需 5 分钟，总共 20 分钟。

多 Agent 的架构价值：**让子任务并行，让每个 Agent 保持干净的上下文，专注于自己的职责范围。**

但多 Agent 不是免费的——它引入了协调开销、通信成本、上下文一致性问题。设计糟糕的多 Agent 系统，协调成本会吃掉并行带来的所有收益，甚至让整体变得更慢更脆。

这篇要讲的，就是三个框架各自怎么解决这个问题。

## 多 Agent 系统的四个核心设计问题

在拆解三个框架之前，先明确多 Agent 系统必须回答的四个架构问题：

1. **角色怎么分离**——谁做什么，怎么定义每个 Agent 的职责边界，防止职责重叠或遗漏
2. **上下文怎么隔离**——Agent 之间的信息怎么分隔，防止一个 Agent 的上下文污染另一个 Agent 的判断
3. **Agent 之间怎么通信**——结果怎么传递，任务怎么分配，协调靠语言还是靠结构
4. **结果怎么汇总**——多个 Agent 的输出怎么合并，冲突怎么解决，最终给用户一个一致的答案

三个框架对这四个问题的答案，揭示了三种完全不同的多 Agent 哲学。

## OpenClaw：两层模式，从子 Agent 到 Agent Teams

### 多 Agent 模式，各有适用场景

OpenClaw 的多 Agent 支持分两个层次，常被混淆，但其实解决的是不同的问题：

**第一层：子 Agent（SubAgent）**

主 Agent 通过 `sessions_spawn` 工具或 `/subagents spawn` 命令派生子 Agent。调用是非阻塞的——主 Agent 发出指令后立刻继续工作，不等待子 Agent 完成。子 Agent 完成后，把结果发回给主 Agent（或直接发到指定的消息渠道）。

这是最常用的模式，适合"主 Agent 需要把某个子任务外包出去，自己继续干别的"这种场景。

关键限制：**子 Agent 只能向主 Agent 汇报，不能和其他子 Agent 直接通信。** 所有协调都要经过主 Agent 这个中间层。

**第二层：路由 Agent（Routed Agents）**

Gateway 层面的多 Agent，每个 Agent 有独立的工作空间（workspace）、会话存储（sessions）和认证配置（auth profiles）。通过 bindings 配置把不同渠道、不同用户路由到不同的 Agent。

适合场景：工作和个人的 Agent 分离、不同用户访问不同 Agent、需要严格安全隔离的场景。

这一层的 Agent 之间完全独立——不共享记忆，不共享上下文，通信需要通过 webhook 或消息队列显式转发。

### 上下文隔离：文件系统是协调层

OpenClaw 的多 Agent 上下文隔离，核心是文件系统隔离：

每个 Agent 有自己的 `workspace`，独立的 `MEMORY.md`、`SOUL.md`、会话记录，存储在 `~/.openclaw/agents/<agentId>/` 下。

**Agent 之间通信的标准方式是文件**——一个 Agent 写结果到某个文件，另一个 Agent 读这个文件。

这很 Unix 哲学——一切皆文件。好处是简单、可预测、不需要额外的通信基础设施。坏处是缺乏实时性，文件读写有延迟，不适合需要即时协调的场景。

### 结果汇总：主 Agent 裁决

子 Agent 的结果发回主 Agent，由主 Agent 裁决。没有自动的冲突解决机制——如果两个子 Agent 给出矛盾的结果，主 Agent 需要自己判断。

## Claude Code：Agent Teams，P2P 通信，文件系统协调

### 两种模式的本质区别

Claude Code 的多 Agent 分两个明确的层次，官方文档直接说明了区别：

**子 Agent（Subagents）**：在单个会话内派发，只能向主 Agent 汇报结果，不能和其他子 Agent 直接通信。适合"快速的、聚焦的、汇报给主 Agent 就完事"的任务。

**Agent Teams（实验性功能）**：多个完全独立的 Claude Code 实例组成团队，每个成员有自己的上下文窗口，可以**直接互相通信**（P2P），不需要经过 Team Lead 中转。

这个 P2P 通信是 Claude Code 多 Agent 设计中最值得关注的特点。

### P2P 通信：去中心化协调

Agent Teams 的通信模型是 P2P 的——任何成员可以直接给其他成员发消息，不需要经过中心节点。

这和 OpenClaw 的星型模型（所有通信经过主 Agent）形成对比。P2P 的优势是减少了通信瓶颈，任何两个 Agent 可以直接协调，不需要等主 Agent 中转。

但 P2P 也有代价：**协调更复杂。** 没有中心节点裁决，冲突解决需要共识机制。目前 Claude Code 的 Agent Teams 还在实验阶段，冲突解决主要靠 Team Lead 介入。

### 上下文隔离：独立实例 + 文件系统

Agent Teams 的每个成员是完全独立的 Claude Code 实例，有独立的上下文窗口、独立的工作目录。

通信方式也是文件系统——一个 Agent 写结果到共享目录，另一个 Agent 读取。和 OpenClaw 类似，但 Claude Code 多了一个机制：**Team Lead 可以主动向成员推送消息**，不需要成员轮询文件。

### 结果汇总：Team Lead 裁决 + 共识

Agent Teams 的结果汇总分两层：

1. **Team Lead 裁决**：Team Lead 收集所有成员的输出，做最终决策
2. **共识机制**（实验性）：对于非关键决策，成员之间可以通过投票达成共识

## Hermes Agent：层级式协作，严格隔离

### 协作模型：层级式

Hermes 的多 Agent 协作是层级式的——有一个明确的 Orchestrator（编排者），负责分配任务和汇总结果。

和 OpenClaw 的星型模型类似，但 Hermes 更严格：

- 子 Agent 只能和 Orchestrator 通信，不能互相通信
- 子 Agent 的权限由 Orchestrator 分配，不能自行扩展
- 子 Agent 的输出必须经过 Orchestrator 审核，才能传递给其他 Agent

### 上下文隔离：沙箱 + 虚拟文件系统

Hermes 的上下文隔离是三个框架里最严格的：

- 每个子 Agent 在独立的沙箱中运行
- 文件系统通过虚拟层隔离——子 Agent 只能看到 Orchestrator 分配给它的文件
- 网络访问通过代理层过滤——子 Agent 只能访问 Orchestrator 授权的地址

这种严格隔离的好处是安全性高，坏处是灵活性低——子 Agent 之间不能直接共享信息，所有通信必须经过 Orchestrator。

### 结果汇总：Orchestrator 审核

Hermes 的结果汇总流程：

1. 子 Agent 完成任务，输出结果
2. Orchestrator 审核结果，检查是否符合预期
3. 审核通过的结果传递给下游 Agent 或汇总
4. 审核不通过的结果退回子 Agent 重新执行

这比 OpenClaw 和 Claude Code 多了一层审核，增加了可靠性，但也增加了延迟。

## 三种多 Agent 哲学的对比

| 维度 | OpenClaw | Claude Code | Hermes Agent |
|------|----------|-------------|-------------|
| 通信模型 | 星型（主 Agent 中转） | P2P + Team Lead | 层级式（Orchestrator） |
| 上下文隔离 | 文件系统 | 独立实例 + 文件系统 | 沙箱 + 虚拟文件系统 |
| 结果汇总 | 主 Agent 裁决 | Team Lead + 共识 | Orchestrator 审核 |
| 灵活性 | 高 | 最高 | 低 |
| 安全性 | 低 | 中等 | 最高 |
| 协调开销 | 中等 | 低（P2P 减少瓶颈） | 高（审核增加延迟） |

## 选择建议

- **需要灵活协作、快速迭代** → OpenClaw 的星型模型最简单，上手最快
- **需要去中心化协调、减少瓶颈** → Claude Code 的 P2P 模式最有潜力，但目前还在实验阶段
- **需要严格安全隔离、合规审计** → Hermes 的层级式模型最可靠，但代价是灵活性

多 Agent 协作的设计，本质上是在**灵活性**和**可控性**之间做取舍。OpenClaw 走灵活路线，Hermes 走可控路线，Claude Code 试图在两者之间找到平衡。

目前三个框架的多 Agent 能力都还不成熟——OpenClaw 缺乏安全机制，Claude Code 的 Agent Teams 还在实验阶段，Hermes 的层级模型过于僵化。多 Agent 协作是 Agent 领域最有挑战性的问题之一，距离"像人类团队一样协作"还有很长的路要走。
