---

## title: Agent 技能设计与实现：从概念到工程化落地\
tags: \[Agent\]\
date: 2026-04-25

# Agent 技能设计与实现：从概念到工程化落地

> **摘要**：本文档系统整理了 AI Agent 技能（Skills）设计的核心概念、架构法则、技术实现路径及工程化最佳实践。内容涵盖从 Prompt 到 Skills 的范式转变、Skills 与 MCP/Tools 的关系、8 条顶级 Skill 架构法则、基于 Tools/MCP/Skills 的代码实现详解，以及利用 Git Worktree 实现并行开发的工程方案。旨在帮助开发者构建精准、可插拔、可进化的 Agent 功能模组。

---

## 目录

 1. 背景与概念：为何需要 Skills？
 2. Prompt 工程的局限性
 3. Skills 的定义与结构
 4. \[核心概念辨析：Prompt vs MCP vs Skills\](#13-核心概念辨析 prompt-vs-mcp-vs-skills)
 5. 核心机制：渐进式披露
 6. 运行机制详解
 7. 为何是未来的主流
 8. 架构法则：编写顶级 Agent Skill 的 8 条建议
 9. 明确 Skill 的定义与结构
10. 磨练描述：精准定义触发机制
11. 写指令，而不是写散文
12. 保持轻量化
13. 设定适当的自由度
14. 不要跳过负面案例
15. 严谨的评估与测试准则
16. 知道什么时候该“退休”技能
17. 技术实现路径：从 Tools 到 MCP 再到 Skills
18. 开发环境配置
19. \[工具调用（Tools/Function Calling）\](#42-工具调用 toolsfunction-calling)
20. \[模型上下文协议（MCP）\](#43-模型上下文协议 mcp)
21. Skills 的实现逻辑
22. 工程化实践：基于 Worktree 的并行开发
23. 单一目录的困境
24. Git Worktree 原理与指令
25. 适用场景与边界
26. 自动化配置损耗
27. 总结与展望

---

## 1. 背景与概念：为何需要 Skills？

在过去的一年里，AI 开发者和用户都在学习如何写更好的 Prompt（提示词）。我们像耐心的老师一样，一遍又一遍地告诉 AI：“你是一个专家，请帮我做这件事，注意背景是……"然而，随着任务复杂度的提升，单纯依赖 Prompt 的模式逐渐暴露出了严重的瓶颈。

### 1.1 Prompt 工程的局限性

在实际应用中，仅靠 Prompt 驱动 Agent 往往会遇到以下崩溃时刻：

- **“失忆”问题**：关掉对话窗口，AI 就忘了你教给它的规则，下次还得重说一遍。Prompt 缺乏持久化的记忆机制，导致每次交互都需要重新注入上下文。
- **“幻觉”问题**：让 AI 处理复杂任务（比如批量重命名文件），它嘴上说“好了”，实际上什么都没干，因为它没有执行权限。模型只能生成文本，无法直接操作文件系统或外部 API。
- **“混乱”问题**：任务太复杂，Prompt 写了 2000 字，AI 反而看晕了，执行得乱七八糟。过长的上下文不仅浪费 Token，还会分散模型的注意力，导致指令遵循能力下降。

如果你遇到过这些问题，那么欢迎来到 **Skills（技能）** 的世界。这是 AI 工程化的下一站，也是将你的个人经验转化为“数字资产”的关键一步。

### 1.2 Skills 的定义与结构

很多人误以为 Skills 只是更高级的 Prompt，这是错误的。在形态上，Prompt 是一段文本，而 **Skills 是一个文件夹**。如果不理解这一点，就无法理解 Skills 的强大。

一个标准的 Skill 文件夹通常包含三个层级的内容，构成了 Agent 的“大脑”、“手脚”和“记忆”：

1. 🧠 **大脑 (SKILL.md)**：

- 这是核心文件。
- 包含 Skills 的名称、描述（给 AI 看的简介）和详细的操作步骤（SOP）。
- 它告诉 AI 什么时候使用该技能，以及如何使用。

1. 💪 **手脚 (Scripts)**：

- 这是执行力。
- 包含 Python 或 Bash 脚本。
- 当 Prompt 只能“动嘴”时，Skills 可以调用脚本去“动手”执行任务（如爬取网页、转换格式、调用 API）。

1. 📚 **记忆 (References)**：

- 这是知识库。
- 包含模板、参考文档或数据表，供 AI 在干活时随时查阅。

**可视化：一个典型的 Skill 结构**

```plaintext
video-downloader/ <-- 这就是 Skill，一个文件夹
├── SKILL.md <-- [必需] 说明书：告诉 AI 什么时候用，怎么用
├── scripts/ <-- [可选] 工具箱：干脏活累活的代码
│ └── batch_download.py <-- 比如：调用 yt-dlp 下载视频的脚本
└── references/ <-- [可选] 参考书：
└── usage_guide.md <-- 比如：参数配置文档
```

### 1.3 核心概念辨析：Prompt vs MCP vs Skills

为了彻底厘清 Skills、Prompt 和 MCP (Model Context Protocol) 的关系，我们可以做一个职场类比：

假设你招聘了一位极其聪明但对公司业务一无所知的实习生（AI Agent）。

- **Prompt（提示词） = “口头临时交代”**
- **场景**：你走到实习生工位旁说：“帮我写个周报。”
- **特点**：临时性、反应式。说完就忘，下次还得再说一遍。
- **局限**：如果任务复杂，你得唾沫横飞说半天，实习生还可能记不住。
- **MCP（模型上下文协议） = “门禁卡与数据库权限”**
- **场景**：实习生说：“老板，我进不去服务器，查不到数据。”你给他开通了 MCP。
- **特点**：连接性。MCP 解决了“能不能连接”的问题，它给了 AI 访问数据库、GitHub 或本地文件的权限。
- **局限**：MCP 是一把钥匙，它不负责教 AI 怎么干活。有钥匙不代表会开飞船。
- **Skills（技能） = "SOP 员工手册”**
- **场景**：你把一本《周报撰写与数据分析 SOP》扔给实习生：“以后写周报就按这个文件夹里的流程来，模板在附件里，自动抓数据的脚本我也写好放进去了。”
- **特点**：固化、可复用、主动式。
- **优势**：不管换哪个实习生（模型），只要把这本手册（Skill）给他，他就能干出同样标准甚至更完美的活。

**一句话总结**：\
Prompt 是你嘴里的话，MCP 是他手里的钥匙，而 Skills 是你印在他脑子里的专业操作手册。

---

## 2. 核心机制：渐进式披露

“把所有要求都写在 Prompt 里不也一样吗？”不一样。这就涉及到了 Skills 设计中最精妙的机制——**渐进式披露 (Progressive Disclosure)**。

### 2.1 运行机制详解

当你的 Agent 挂载了 100 个 Skills 时，它并不是把这 100 本手册的内容一次性全部塞进脑子（Context Window）里，那样既浪费钱（Token），又会让 AI 变笨。

Skills 的运行机制是这样的：

1. **看目录（Metadata）**：

- AI 首先只读取所有 Skills 的“名字”和“简介”。
- 这只占极少的 Token。
- 作用：让 Claude 知道“自己拥有哪些技能”，用于后续的意图匹配和技能触发判断。

1. **按需加载（On-Demand Loading）**：

- 当你问“帮我把这个视频转成 GIF"时，AI 发现 `video-processing` 这个 Skill 的简介匹配了。
- 它才会去读取这个 Skill 文件夹里详细的 `SKILL.md` 操作指南。
- 作用：为 AI 提供清晰、可复用的任务执行逻辑，将“反复解释的 Prompt"固化为稳定的能力指令。

1. **执行工具（Execution）**：

- 如果在操作指南里发现需要运行代码，它才会去加载 `scripts/` 里的 Python 脚本并执行。
- 作用：一个复杂的 skill 可能包含多个文件，形成一个完整的知识库，实现完整的任务闭环。

这种机制让 AI 能够像人类专家一样：**脑子里装着索引，需要时才去查阅具体的百科全书。** 这使得 AI 可以同时拥有成千上万种技能，而不会“死机”。

### 2.2 为何是未来的主流

从 Prompt 到 Skills，标志着我们从“调教 AI"走向了"AI 工程化”。

1. **复用性（Reusability）**：

- 你写好的一个“深度研报生成 Skill"，可以直接打包发给同事，或者上传到 Coze 商店赚取收益。
- 你的经验变成了可流通的代码资产。
- Skill 是三位一体（Meta + Prompt + Code）的结构，让 Agent 的能力变得像代码库一样，可以被版本控制（Git 管理）、独立测试（单独运行 Skill）、社区共享（直接 Copy 文件夹即可使用）。

1. **稳定性（Stability）**：

- Prompt 容易产生幻觉，但 Skill 里面封装的 Python 脚本是逻辑严密的。
- 用 Skill 让 AI 调用 FFmpeg 处理视频，成功率远高于让 AI 自己“想象”怎么处理视频。

1. **自我进化（Evolution）**：

- 高级的 Skills 系统甚至可以包含“自我反思”机制。
- 每次任务失败，Skill 可以记录错误日志，更新自己的 SOP，让下一次执行更聪明。

---

## 3. 架构法则：编写顶级 Agent Skill 的 8 条建议

在 AI Agent 领域，很多开发者都陷入了一个瓶颈：**明明模型底座一直在升级，为什么我的 Agent 还是经常“间歇性降智”？** 其实，Agent 并不缺“大脑”，缺的是好用的“肌肉”——也就是我们常说的 **Skills（技能）**。Skill 已成为 Agent 中最常用的扩展点。它们灵活、易于制作且易于分发。但这种灵活性也让人难以捉摸：什么样的技能值得做？编写好技能的秘诀是什么？以下是来自实战经验的 8 条深度建议。

### 3.1 明确 Skill 的定义与结构

Skill 绝不仅仅是一个简单的 `SKILL.md` 文件，它是一个**结构化的文件夹**。一个标准的技能包应当具备清晰的目录层级，以便 Agent 按需调用：

```plaintext
my-skill/
├── SKILL.md ← 唯一必需的文件
├── scripts/ ← Agent 可以运行的可重用代码
├── references/ ← Agent 在需要时读取的文档
└── assets/ ← 输出中使用的模板、图像或文件
```

**一个 Skill 由 3 个层级组成：**

1. **名称和描述 (Frontmatter)**：进入每个 Prompt，告诉 Agent 何时使用该技能。
2. **SKILL.md 正文**：Frontmatter 下方的 Markdown 指令，告诉 Agent 如何执行任务。
3. **资产层（可选）**：包括 `scripts/`、`references/` 和 `assets/` 文件夹。

**技能通常分为两类：**

- **能力型 (Capability)**：帮助 Agent 完成基础模型无法稳定完成的任务（如 PDF 表单填充）。随着模型改进，这类技能可能会变得多余。
- **偏好型 (Preference)**：编码你的特定工作流（如团队的代码审查步骤）。这些是持久的，但需要与你的实际流程同步。

### 3.2 磨练描述：精准定义触发机制

`SKILL.md` 中的描述是**触发机制**。如果描述模糊，Agent 不知道何时激活；如果太宽泛，技能会在每个请求中触发。描述必须包含 **“做什么 (What)"** 和 **“何时用 (When)"**。

**优秀描述示例：**

类型描述示例文档处理“创建、编辑和分析 .docx 文件，用于修订、评论、格式化或文本提取”API 调用“在编写调用 Gemini API 进行文本生成、多轮对话、图像生成或流式传输的代码时使用”

**提示**：仅仅通过优化描述，就能带来 50% 的性能提升。

### 3.3 写指令，而不是写散文

Agent 很聪明，你的任务是告诉它那些它还不知道的事情。研究表明，过长且包含过多背景信息的指令反而会损害性能。

- **使用指令 (Directives)**：使用“始终使用 `interactions.create()`"，而不是"Interactions API 是推荐的方法”。前者是指令，后者是 Agent 不会采取行动的冷知识。
- **示例优先**：5 行代码片段的效果远好于 5 段文字解释。
- **解释“为什么”**：当规则很重要时，说明原因。“使用模型 X，模型 Y 已弃用并会返回错误”，这有助于 Agent 在特定测试案例之外进行泛化推理。
- **不要过度拟合 (Overfit)**：避免那些只为了通过三个特定测试 Prompt 的“微调”。要编写能经受住数百万次调用的技能。

### 3.4 保持轻量化

不要把所有东西都塞进一个文件。Agent 是分层加载信息的：

1. **始终加载**：`SKILL.md` 的 Frontmatter（名称 + 描述）。
2. **触发后加载**：`SKILL.md` 的正文（建议保持在 **500 行以内**）。
3. **按需加载**：参考文件 (references)、脚本 (scripts)、资产 (assets)。

**Tip**：如果参考文件超过 500 行，请在顶部添加带有“行号提示 (line hints)"的目录，以便 Agent 快速定位。

### 3.5 设定适当的自由度

创建技能时常见的错误是将其变成死板的步骤工作流：“步骤 1：读取文件。步骤 2：解析 JSON……"当你规定了每一步，就剥夺了 Agent 适配、从错误中恢复或寻找更好方法的能力。

**告诉 Agent 要实现什么：**

- ❌ “步骤 1：读取配置文件。步骤 2：查找数据库 URL。步骤 3：更新端口号。步骤 4：写回文件。”
- ✅ “将配置文件中的数据库端口更新为用户指定的值。”

**提供约束，而非程序：**

- ❌ “步骤 1：创建分支。步骤 2：进行更改。步骤 3：运行测试。步骤 4：开启 PR。”
- ✅ “在开启 PR 之前始终运行测试。严禁直接推送到 main。”

如果步骤极其精确且不可变，那是**脚本**的任务，而不是**技能**的任务。

### 3.6 不要跳过负面案例

思考一下技能**不应该**触发的情况。类似“用于任何编码任务”的描述会劫持所有请求。

> “在处理 PDF 文件时使用。**请勿**用于常规文档编辑、电子表格或纯文本文件。”

必须同时测试“应触发”和“不应触发”的情况，否则你会让技能在错误的道路上过度优化。

### 3.7 严谨的 6 个评估与测试准则

跑通一次是不够的，你必须进行评估：

1. **手动多轮测试**：使用不同 Prompt 手动运行几次，观察它在哪里崩溃。是否假设了某个依赖项存在？是否跳过了步骤？
2. **定义可衡量的成功**：输出是否可编译？是否使用了正确的 API？是否遵循了步骤？评估结果而非路径。
3. **准备 10-20 个测试 Prompt**：混合“应处理”、“应忽略”和“棘手的边缘案例”。每个 Prompt 都要有自己的成功标准。
4. **进行多次试验**：Agent 输出具有随机性。每个 Prompt 运行 3-5 次，观察结果的分布而非单次过关。
5. **隔离运行**：每次测试使用干净的环境，防止上下文“出血 (Context bleeding)"掩盖真实的失败。
6. **优先修复描述**：大多数问题出在触发机制，而非正文指令。

### 3.8 知道什么时候该“退休”技能

定期在没有技能的情况下运行评估。如果评估通过，说明基础模型已经吸收了该技能的价值，该技能已不再必要。

对于**能力型技能**尤其如此，随着模型的改进，差距会逐渐缩小。当模型变强，果断退休旧技能，保持 Agent 的轻盈。

---

## 4. 技术实现路径：从 Tools 到 MCP 再到 Skills

本章节将手把手教大家如何做一个 Agent，由此会让大家更加理解 Agent 的难点到底在哪。我们将沿着 **Tools -&gt; MCP -&gt; Skills** 的技术演进路线进行实现。

### 4.1 开发环境配置

在开发中，不同项目需要不同版本的 Python（例如 3.10、3.12）。为了方便管理多版本 Python，我们使用 pyenv。

**官方地址**：https://github.com/pyenv/pyenv

**macOS 使用 Homebrew 安装：**

```bash
brew update
brew install pyenv
```

**或者通过脚本安装：**

```bash
curl https://pyenv.run | bash
```

**Linux 和 Windows 安装：**

```bash
curl -fsSL https://pyenv.run | bash
# Windows 使用 pyenv-win：
# 1. 打开 PowerShell（管理员权限）。
# 2. 执行安装命令：
Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1" -OutFile "./install-pyenv-win.ps1"; &"./install-pyenv-win.ps1"
```

**安装完成后，运行以下命令查看版本：**

```bash
pyenv --version
```

**常见命令：**

```bash
# 查看可安装的 Python 版本
pyenv install --list | grep 3.12
# 安装 Python 3.12.0
pyenv install 3.12.0
# 查看已安装的版本
pyenv versions
# 设置全局 Python 版本
pyenv global 3.12.0
# 为当前目录设置 Python 版本
pyenv local 3.12.0
```

**Python 包管理工具：uv**\
uv 是一个轻量级的 Python 包管理工具，用于管理虚拟环境和依赖包，类似 pip + venv 的组合。

**官方地址**：https://github.com/astral-sh/uv

**安装：**

```bash
# macOS / Linux
curl -fsSL https://uv.dev/install.sh | bash
# 或者使用 pip 安装
pip install uv-cli

# Windows (PowerShell)
pip install uv-cli
```

**常用命令：**

```bash
# 初始化项目（自动创建虚拟环境）
uv init
# 查看当前项目使用的 Python 版本
uv run python --version
# 安装依赖包
uv add requests flask
uv add openai
# 卸载依赖包
uv remove requests
# 锁定当前环境依赖（生成 uv.lock）
uv lock
# 根据锁文件安装依赖
uv sync
```

**API Key 配置**\
我们需要配置大模型和地图服务的 Key 到 `.env` 文件中：

```bash
echo "DEEPSEEK_API_KEY=youkey" > .env
echo "AMAP_API_KEY=youkey" >> .env
```

### 4.2 工具调用（Tools/Function Calling）

大模型本身只能做文本理解和生成，无法直接访问数据或执行外部逻辑，例如查询天气、搜索景点、计算路线等。**Tools（函数调用）** 机制的作用，是由应用侧提供一组可调用的函数，在模型推理过程中，由模型决定是否需要调用这些函数、以及调用哪一个、使用什么参数。

#### 4.2.1 Tools 的调用流程

Tools 的调用并不是一次完成的，而是一个多轮交互过程：

1. **发起第一次模型调用**：应用程序首先向大模型发起一个包含用户问题与模型可调用工具清单的请求。
2. **接收模型的工具调用指令**：若模型判断需要调用外部工具，会返回一个 JSON 格式的指令，用于告知应用程序需要执行的函数与入参；若模型判断无需调用工具，会返回自然语言格式的回复。
3. **在应用端运行工具**：应用程序接收到工具指令后，需要运行工具，获得工具输出结果。
4. **发起第二次模型调用**：获取到工具输出结果后，需添加至模型的上下文（messages），再次发起模型调用。
5. **接收来自模型的最终响应**：模型将工具输出结果和用户问题信息整合，生成自然语言格式的回复。

#### 4.2.2 为什么要使用 Tools

在早期没有标准化工具调用能力时，Agent 主要依赖提示词驱动。这种方式在工程上存在明显问题：

1. **强耦合**：函数设计、调用规则、解析逻辑和提示词紧密绑定，一旦业务变化，就需要同时修改代码和提示词。
2. **稳定性不足**：模型输出的是自然语言，哪怕格式略有变化，解析逻辑就可能失效，线上风险很高。
3. **提示词复杂且难维护**：为了约束模型行为，提示词往往变得又长又重，阅读和维护成本持续上升。

如果不想在提示词里面做上述动作，那么就要在微调侧做投入，只不过当大模型原生支持 Tools（Function Calling）后，依旧是最优解：**工具调用能力被以标准化，包含明确的名称、功能描述和参数结构。**

#### 4.2.3 典型案例：旅行 Agent 实现

旅行规划是最经典的 Tools 案例。一个可用的旅行 Agent，至少需要具备景点搜索、天气查询、酒店筛选、行程生成和路线规划等能力。

**实现思路：**\
为了构建这个旅行智能体，我们采用了模块化的代码设计，将“能力实现”与“智能决策”解耦。核心包含三个主要部分：

**一、标准化的工具定义**\
我们没有为模型专门写一套复杂的配置文件，而是直接利用 Python 原生的语法特性来定义工具。在 `TravelTools` 类中，每一个方法都遵循以下规范：

1. **类型提示**：明确声明每个参数和返回值的类型。
2. **文档字符串**：用自然语言详细描述了“这个函数是做什么的”、“每个参数的具体含义”以及“返回的数据结构”。
3. **异步设计**：涉及网络请求的操作均采用 async/await。

```python
class TravelTools:
"""
旅游规划助手工具类
"""
def __init__(self, amap_api_key: Optional[str] = None, request_delay: float = 0.2):
self.amap_api_key = amap_api_key or os.getenv("AMAP_API_KEY")
# ...

async def estimate_travel_cost(self, city: str, days: int, hotel_level: str = "舒适",
attractions: Optional[List[str]] = None) -> Dict[str, Any]:
"""
估算旅游费用（不含往返交通）
使用场景：
- 制定旅游预算
- 比较不同档次的旅游费用
- 规划旅游支出
Args:
city: 旅游城市名称，如'西安'、'北京'、'上海'
days: 旅游天数（含当天），如 3 表示 2 晚 3 天
hotel_level: 住宿档次，可选值：
- '经济': 150 元/晚（快捷酒店）
- '舒适': 300 元/晚（三星级酒店，默认）
- '豪华': 500 元/晚（四星级及以上）
attractions: 计划游览的景点列表（可选），用于估算门票费用
Returns:
费用估算字典，包含：
- city: 城市名称
- days: 旅游天数
- breakdown: 费用明细（住宿、餐饮、交通、门票）
- total: 总费用
- tips: 温馨提示
"""
# ... 具体实现逻辑 ...
pass
```

**二、自动化注册与 Schema 生成**\
为了连接 Python 代码和大模型，我们实现了一个 `ToolRegistry` 工具类。它的核心职责是“翻译”和“管理”：

1. **自省与生成**：利用 Python 的反射机制，自动读取工具函数的签名和文档，将其动态转换为大模型能够理解的 OpenAI Function Calling 格式（JSON Schema）。
2. **统一执行**：提供了一个 `execute_tool` 方法。当模型发出调用指令时，Registry 负责解析参数，找到对应的 Python 函数执行，并将结果序列化为 JSON 格式返回。

```python
@dataclass
class Tool:
"""工具定义数据模型"""
name: str # 工具名称/函数名
description: str # 工具描述（用于大模型理解）
parameters: Dict[str, Any] # 参数 JSON Schema
function: Callable # 实际的执行函数

def to_dict(self) -> dict:
"""转换为 OpenAI Function Calling 格式"""
return {
"type": "function",
"function": {
"name": self.name,
"description": self.description,
"parameters": self.parameters
}
}

class ToolRegistry:
# ...
def register_from_class(self, cls, ...):
"""从类中自动注册异步方法为工具"""
# 利用 Python 的反射机制（Inspect 模块）
# 自动读取工具函数的签名和文档
# ...
pass

async def execute_tool(self, tool_call: ToolCall) -> ToolResult:
"""执行单个工具调用"""
# ...
pass
```

**三、ReAct 循环**\
Agent 的运行逻辑是一个经典的 While 循环，模拟了“观察 - 思考 - 行动”的过程：

```python
# ... 初始化 messages ...
while count < 15:
count = count + 1
# 发送请求给大模型
result = await llm_client_with_tools(messages, tool_registry.get_tools())
assistant_message = result.choices[0].message

# 检查是否有工具调用
if assistant_message.tool_calls:
# 1. 添加 assistant 消息到历史
messages.append({
"role": "assistant",
"content": assistant_message.content,
"tool_calls": [...]
})
# 2. 执行所有工具调用
for tool_call in assistant_message.tool_calls:
# 执行工具
tool_result = await tool_registry.execute_tool(...)
# 3. 添加工具结果到历史
messages.append({
"role": "tool",
"tool_call_id": tool_call.id,
"content": tool_result.content
})
# 继续下一轮循环，将工具结果带给模型
continue
else:
# 没有工具调用，输出最终回复
print(assistant_message.content)
break
```

### 4.3 模型上下文协议（MCP）

MCP（Model Context Protocol）是一种用于规范大模型与外部能力交互方式的协议。它关注的不是某一个具体工具，而是如何以统一、标准的方式，把外部系统的能力、数据和上下文暴露给模型使用。

**如果说 Tools 解决的是“模型如何调用一个函数”，那么 MCP 解决的是“模型如何与一个长期存在、可复用的能力服务交互”。**

#### 4.3.1 为什么会出现 MCP

随着 Agent 应用越来越复杂，仅靠应用内定义的 Tools 会暴露出几个问题：

1. **复用困难**：能力通常绑定在单个项目中，跨项目或跨 Agent 使用时需要重复实现。
2. **生命周期不匹配**：Tools 通常随一次调用存在，而很多能力本身是长期运行的服务，例如数据库访问或搜索引擎。
3. **边界和治理难**：随着可调用能力增多，权限、审计和隔离难以统一管理。

MCP 提供了一套标准化协议，把能力从单个应用中抽离，形成独立、可复用、可治理的服务层。

#### 4.3.2 MCP Server 与 MCP Client

MCP 包含两个角色：

- **MCP Server**：对外提供能力和上下文的服务端。
- **MCP Client**：运行在应用或 Agent 中，负责与 Server 通信。

**MCP Server 端代码示例（基于 FastMCP）：**

```python
from typing import Dict, List, Optional, Any, Annotated
from pydantic import Field
from fastmcp import FastMCP
# 导入 TravelTools 类
from code.Function_Calling.tools import TravelTools

mcp = FastMCP(name="旅游规划助手")
# 初始化 TravelTools 实例
travel_tools = TravelTools()

@mcp.tool("get_current_weather", description="获取当前天气信息")
async def get_current_weather(
city: Annotated[str, Field(description="城市名称，如'西安'")],
province: Annotated[str, Field(description="省份名称，如'陕西'")]) -> Dict[str, Any]:
try:
weather = await travel_tools.get_weather(city, province)
return weather.to_dict()
except Exception as e:
return {"error": str(e)}

@mcp.tool("geocode", description="地理编码：将地址转换为经纬度坐标")
async def geocode(
address: Annotated[str, Field(description="地址或地点名称，如'兵马俑'、'大雁塔'、'西安市钟楼'")],
city: Annotated[str, Field(description="城市名称（可选），用于限定搜索范围，如'西安'、'北京'")] = "") -> Dict[str, Any]:
try:
location = await travel_tools.geocode(address, city)
return location.to_dict()
except Exception as e:
return {"error": str(e)}

# ... 其他工具定义类似 ...

if __name__ == '__main__':
mcp.run(transport="http", port=8001)
```

**MCP Client 端代码示例：**

```python
import asyncio
import json
import os
from openai import OpenAI
from fastmcp import Client
from code.Working_with_LLMs.llm_client import llm_client_with_tools

SYSTEM_PROMPT = """你是一个专业的旅游规划助手..."""

async def chat_with_mcp(user_input: str):
client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
# 连接到你的服务器
mcpClient = Client("http://127.0.0.1:8001/mcp")
await mcpClient.__aenter__()

# 列出可用工具
mcp_tools = await mcpClient.list_tools()
llm_tools = []
for tool in mcp_tools:
llm_tools.append({
"type": "function",
"function": {
"name": tool.name,
"description": tool.description,
"parameters": tool.inputSchema,
},
})

# 加载工具，第一次调用，让模型自己判断是否使用工具
messages = [{"role": "system", "content": SYSTEM_PROMPT},
{"role": "user", "content": user_input}]
count = 0
while count < 15:
count = count + 1
result = await llm_client_with_tools(messages, llm_tools)
assistant_message = result.choices[0].message
content = assistant_message.content or ""

# 检查是否有工具调用
if assistant_message.tool_calls:
# 构建 tool_calls 记录
tool_calls_data = [
{
"id": tc.id,
"type": tc.type,
"function": {
"name": tc.function.name,
"arguments": tc.function.arguments
}
} for tc in assistant_message.tool_calls
]
# 添加到消息历史
messages.append({
"role": "assistant",
"content": content,
"tool_calls": tool_calls_data
})
# 执行所有工具调用
for tool_call in assistant_message.tool_calls:
tool_name = tool_call.function.name
try:
arguments = json.loads(tool_call.function.arguments)
except json.JSONDecodeError:
arguments = {}
# 执行工具
tool_result = await mcpClient.call_tool(tool_name, arguments)
# 添加工具结果
messages.append({
"role": "tool",
"tool_call_id": tool_call.id,
"content": json.dumps(tool_result.structured_content, ensure_ascii=False)
})
continue
else:
count = 15
print(content)

if __name__ == '__main__':
asyncio.run(chat_with_mcp("西安 2 日游"))
```

### 4.4 Skills 的实现逻辑

虽然 MCP 解决了多 Agent 对 Tools 的调用解耦，但 Agent 的老大难问题依旧没被解决：**Tools 多了，调用不准；在执行过程中，无论模型怎么循环依旧不稳定的问题。**

Anthropic 官方文档给出了 Skills 的解决方案，他包含三个层级，从抽象到具体：

1. **元数据**：Skill 的名称、描述、标签等信息。
2. **指令**：Skill 具体的指令。
3. **资源**：Skill 附带的相关资源（比如文件、可执行代码等）。

#### 4.4.1 深度解析：渐进式披露

Claude Skills 设计遵循了一个非常重要的原则：**Progressive Disclosure**。

- **第一层：元数据（始终加载）**\
  Claude 在启动时会扫描所有已安装的 Skills，并加载这些元数据，将其纳入系统提示（System Prompt）中。

```yaml
---
name: douyin-summary
description: 抖音视频总结助手。当用户提供抖音（douyin.com 或 v.douyin.com）视频链接并请求总结、获取文案或了解视频内容时，使用此技能。
---
```

- **第二层：核心指令（触发时加载）**\
  当用户的请求与某个 skill 的描述相匹配时，Claude 会通过 bash 从文件系统中读取对应的 `SKILL.md` 文件，并将其完整内容加载进当前对话上下文。

```markdown
# 抖音视频总结助手
此技能用于获取和总结抖音视频的内容。
## 工作流程
当用户提供抖音链接时：
1. **识别抖音链接**: 检测用户输入中的 douyin.com 或 v.douyin.com 链接
2. **调用脚本获取内容**: 使用 `scripts/fetch_douyin.py` 获取视频转录/文案
3. **总结内容**: 基于获取的文本内容，提取核心观点、关键信息或有趣之处
4. **友好输出**: 以简洁易懂的方式呈现给用户
```

- **第三层：代码与资源（按需加载）**\
  一个复杂的 skill 可能包含多个文件，形成一个完整的知识库。

```plaintext
└── skill-name/
├── meta.json # [路由层] 告诉模型这个技能是干嘛的
├── skill.md # [逻辑层] 包含了 System Prompt 和 SOP
└── scripts/ # [执行层] 实际干活的 Python/Bash 脚本
```

#### 4.4.2 在 DeepSeek 上实现 Skills 引擎

Skills 本质上只是一种文件结构约定。只要我们编写代码去解析这些文件，并根据 meta.json 的描述与大模型交互，就可以让 DeepSeek、OpenAI 或任何具备 Tool Calling 能力的模型 拥有“加载 Skills"的能力。

**第一步：读取元数据**

```python
def load_skills_from_meta():
"""扫描目录，从 meta.json 加载技能元数据"""
# 示例：假设我们读取到了 simple_weather_skill
with open("./simple_weather_skill/meta.json", "r", encoding="utf-8") as f:
meta = json.load(f)
# 构造兼容 OpenAI/DeepSeek 格式的工具定义
return [{
"type": "function",
"function": {
"name": meta["name"],
"description": meta["description"],
"parameters": {
"type": "object",
"properties": {},
"required": []
},
},
}]
```

**第二步：意图识别与上下文注入**

```python
# 1. 准备工具列表
skills = load_skills_from_meta()
# 2. 发送请求给 DeepSeek，让其选择
messages = [{"role": "user", "content": user_input}]
result = client.chat.completions.create(
model="deepseek-chat",
messages=messages,
tools=skills # 关键点：把 Skill 描述当作 Tools 传进去
)

# 检查模型是否想调用 Skill
if result.choices[0].message.tool_calls:
skill_name = result.choices[0].message.tool_calls[0].function.name
print(f"模型命中技能：{skill_name}")
# 读取对应的 Prompt 模板
with open(f"./{skill_name}/skill.md", "r") as f:
skill_prompt = f.read()
# 【核心魔法】：构建一个新的对话上下文，使其立即拥有该技能的知识
skill_messages = [
{"role": "system", "content": skill_prompt}, # 注入技能 Prompt
{"role": "user", "content": user_input} # 重放用户问题
]
# 此时，DeepSeek 已经变身为“天气专家”，准备好执行具体脚本了
```

**第三步：执行脚本**

```python
def execute_script(script_path, args=None):
"""一个通用的脚本执行器工具"""
cmd = ["python", script_path] + (args or [])
res = subprocess.run(cmd, capture_output=True, text=True)
return res.stdout
```

通过这套机制，我们就在 DeepSeek 上完美模拟了 Claude 的 Skills 流程：**路由 -&gt; 加载 Prompt -&gt; 执行脚本。**

---

## 5. 工程化实践：基于 Worktree 的并行开发

在 AI Agent 普及的背景下，开发者的工作模式发生了转变。当多个 Agent 并行运行时，开发者的核心工作不再是手写代码，而是**任务拆解、任务分配、成果审核**。而 **Git Worktree** 是这套全新工作模式的底层支撑。

### 5.1 单一目录的困境

当你启动 Claude 执行代码重构任务时，必然会遇到一个尴尬问题：这项任务耗时不短，而后续的麻烦早已注定。

- **等待困境**：你要么盯着不断滚动的日志干等，全程小心翼翼，生怕随意操作导致任务异常中断。
- **冲突困境**：要么趁等待间隙随手优化小细节。可等 AI Agent 执行完毕、比对代码差异后，往往会自主回退你的修改，它会判定这些内容超出既定任务范围，直接抹除你的临时改动。

两种选择，本质是同一个问题的不同表现：**你与 AI Agent 共用同一个工作目录，而单一工作目录，同一时间只能承载一套开发思路与代码变更。**

### 5.2 Git Worktree 原理与指令

**工作树（worktree）** 是同一项目的第二操作视图，绑定独立分支，让你和 AI Agent 并行协作、互不干扰。

**一句话读懂工作树**：\
工作树，是指向同一个 Git 仓库的独立工作目录，各自绑定专属分支，完全相互隔离。

**创建命令：**

```bash
# 在主仓库目录内执行
git worktree add .worktrees/myrepo-auth -b feature/auth
```

该命令会在仓库内自动创建 `.worktrees/myrepo-auth` 文件夹，新建并绑定 `feature/auth` 分支，**完全不改动原有工作目录的任何内容**。

**Claude Code 原生支持：**

```bash
claude --worktree feature-auth
```

指令后填写自定义工作树名称即可，Claude 会自动在 `.claude/worktrees/feature-auth` 目录生成独立工作区。

**工作树常用指令速查表：**

```bash
# 基于新分支创建工作树
git worktree add .worktrees/myrepo-auth -b feature/auth

# 绑定已有分支创建工作树
git worktree add .worktrees/myrepo-hotfix hotfix/login

# 查看本地所有工作树列表
git worktree list

# 用完删除工作树（存在未提交变更时添加 --force 强制删除）
git worktree remove [--force] .worktrees/myrepo-auth

# 手动删除文件夹后，清理失效的工作树元数据
git worktree prune
```

**核心认知：**

- 分支是仓库版本历史中带命名的提交链路，仅存在于版本记录中，无本地实体路径。
- 工作树是本地磁盘的实体文件夹，是可视化编辑指定分支代码的独立载体。
- 删除工作树不会删除对应分支。
- 跨工作树提交实时同步（共享同一套 `.git` 数据库）。

### 5.3 适用场景与边界

这套隔离机制存在明确限制：**工作树实现的是分支并行，而非 Agent 并行**。

- **适用场景**：多分支并行开发。例如，你启动 AI Agent 在 `feat/auth` 分支执行十分钟级别的迭代开发，不想空等，也不愿切换分支打乱当前开发进度。借助工作树，新建 `feat/billing` 专属工作区，同步开展另一项开发工作。
- **不适用场景**：同一分支运行多个 Agent。若你在 `feat/frontend-redo` 分支开展大规模前端重构，想要同时启用三个 Agent 并行开发，直接为同一分支创建多个工作树的思路完全行不通。正确解决方案是**任务拆解**，基于主分支拆分多个子分支，为每个子分支单独配置工作树。

### 5.4 自动化配置损耗

工作树仅同步 Git 追踪的代码文件，所有写入忽略配置的内容，都不会自动同步至新工作区。这带来了隐性配置成本：

- 依赖目录：`node_modules`、虚拟环境 `.venv` 等。
- 构建产物：`dist`、`.next` 等。
- 环境配置：`.env` 等本地私密配置文件。
- 端口冲突：多个工作树同时运行本地开发服务，会抢占同一端口。

**最优方案：脚本 + Skill 双向结合**

- **Shell 脚本**：承接机械性底层操作。创建工作树、批量同步环境配置、按规则生成独立端口、执行依赖安装。
- **Claude Code Skill**：承接决策性上层操作。基于自然语言描述生成分支名、制定合并策略、生成合并请求文案。

**开箱即用的工作树管理工具集：**\
可以通过 `npx @thinkvelta/claude-worktree-tools` 一键部署。该工具集包含：

- 脚本文件：生成 `scripts/wt-setup.sh` 底层脚本。
- 自定义 Skill：在 `.claude/skills/` 目录写入全套智能指令（`/wt-open`, `/wt-merge`, `/wt-close` 等）。

**完整落地流程：**

```bash
# 一次性部署
npx @thinkvelta/claude-worktree-tools

# 启动 Claude Code 会话
claude

# 项目首次适配
> /wt-adopt

# 输入任务描述，一键创建独立工作树并行开发
> /wt-open "为鉴权接口添加访问频率限制"

# 任务完成：将子分支代码合并至主分支
> /wt-merge feat/auth

# 销毁工作区并推送代码至远程仓库
> /wt-close --push
```

---

## 6. 总结与展望

从“写 Prompt"到“架构 Skill"，本质上是从文科思维向工程思维的跨越。在 Agent 的竞争中，不再是看谁的指令写得更华丽，而是看谁能构建出一套精准、可插拔、可进化的功能模组。

**核心要点回顾：**

1. **概念升级**：Prompt 是口头指令，MCP 是门禁卡，Skills 是 SOP 操作手册。
2. **架构法则**：遵循 8 条建议，包括精准描述、指令化、轻量化、设定自由度等。
3. **技术演进**：Tools 是能力基石，MCP 是协议层，Skills 是封装层。
4. **工程实践**：利用 Git Worktree 实现人机并行开发，通过脚本 + Skill 自动化配置损耗。

当你开始思考技能的解耦与评估时，你的 Agent 才真正拥有了灵魂。任何理论优秀、实操繁琐的工具，都可以通过自定义智能 Skill 抹平使用门槛。利用你正在运行的 AI Agent，搭建服务于更多 Agent 的自动化工具，形成良性循环，这是未来的主流方向。

不要让 AI Agent 与你挤在同一个工作区。给它一片独立空间，再让自动化工具，自动完成后续所有环境搭建。