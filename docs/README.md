# NoteAI - AI驱动的Markdown笔记知识库管理

## 项目简介

NoteAI 是一个功能完善的 AI 驱动 Markdown 笔记知识库管理桌面应用。使用**Tauri**作为前端框架，结合 HTML/CSS/JS 构建现代化界面，集成 LangChain 实现 AI 相关功能。

## 核心功能

### 1. 网络文章批量下载与转换

- 支持批量输入 URL（每行一个）
- 自动下载网页内容并转换为 Markdown
- AI 辅助模式：智能排版、内容净化
- 支持下载图片（可选）

### 2. 多格式文件转换

- 支持格式：PDF、DOCX、PPTX、TXT → Markdown
- 自动内容净化与格式优化
- AI 辅助模式：智能排版增强

### 3. 主题提取与笔记整合

- 从 Markdown 文件自动提取主题
- 三种整合策略：
  - **机器学习分类**：基于文件名的主题聚类
  - **RAG 增强**：检索增强生成
  - **长上下文**：直接处理所有文档
- 按主题组织生成结构化笔记

### 4. 文件浏览与编辑

- 侧边栏文件树浏览
- 双栏模式：Markdown 编辑器 + 实时预览
- CodeMirror 6 编辑器支持：
  - Markdown 语法高亮
  - 深色/浅色主题
  - 自动保存

## 技术架构

### 技术栈

| 类别 | 技术 |
| --- | --- |
| 桌面壳 | Tauri 2 + 系统 WebView |
| 前端 | HTML5、CSS3、JavaScript（`webui/`） |
| 富文本 / 编辑 | Tiptap、CodeMirror 6 等（以 `webui/` 实际引用为准） |
| 本地后端 | Python 3.10+，sidecar 进程（stdin/stdout JSON，见 `python/sidecar/`） |
| AI | LangChain、LangChain-OpenAI 等（见 `pyproject.toml`） |
| 文档 / 解析 | BeautifulSoup4、python-docx、PyMuPDF、mammoth 等 |
| 工作区文件监听 | **watchdog**（已列入 `pyproject.toml`；缺失时 sidecar 会打一条 stderr 说明） |
| 依赖管理 | **以 `pyproject.toml` 为唯一事实来源**；推荐 `uv` + `uv.lock` |

### 项目结构

```
NoteAI/
├── README.md                 # 根目录快速开始（本文件为详细说明）
├── run.py                    # 开发入口：检查依赖后执行 cargo tauri dev
├── pyproject.toml            # Python 依赖与 pytest 配置（主清单）
├── uv.lock                   # uv 锁文件（使用 uv 时）
├── requirements.txt          # 仅含可编辑安装 -e . 说明，不重复列包
├── config/                   # 应用与用户配置（含系统目录下的状态说明见下文）
├── webui/                    # 前端静态资源
│   ├── index.html
│   ├── js/ / css/
│   └── （app.py 已删除）
├── python/
│   ├── main.py               # Tauri 调用的 sidecar 进程入口
│   └── sidecar/              # JSON-RPC 路由、mixins 按功能拆分
│       ├── server.py         # SidecarServer、handle_request、文件监听
│       └── mixins/           # 配置、工作区、下载、标签、主题、链接等
├── src-tauri/                # Rust：窗口、py_call、打包资源（含 python/**）
├── modules/                  # 业务模块：下载、转换、整合、预览等
├── prompts/                  # LLM 提示词
├── utils/                    # 工具、主题分配、链接索引等
├── tests/                    # 单元 / 集成测试
│   └── integration/          # 路径与 sidecar 契约等
└── docs/                     # API、使用说明等
```

## 安装说明

### 环境要求

- **Python 3.10+**
- macOS / Windows / Linux
- 开发 Tauri 应用需 **Rust** 与 Tauri CLI（见根目录 `run.py` 的提示）

### 安装步骤

1. 克隆项目

```bash
git clone https://github.com/Miles128/NoteAI.git
cd NoteAI
```

1. 创建虚拟环境并安装依赖（**推荐**）

```bash
uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv sync
# 含开发依赖（pytest 等）：
uv sync --extra dev
```

1. 若使用 **pip**（从仓库根目录，依赖仍来自 `pyproject.toml`）

```bash
pip install -e .
pip install -e ".[dev]"
```

`requirements.txt` 已改为可编辑安装说明，**不再**与 `pyproject.toml` 重复维护平铺版本号。

### 运行应用

开发与调试（启动 Tauri + Python sidecar，在**仓库根目录**）：

```bash
python run.py
```

（`webui/app.py` 已删除；旧 HTTP 调试入口不再保留。）

## 使用指南

### 首次使用

1. **设置工作区**
   - 点击「打开工作区」按钮
   - 选择一个文件夹作为工作目录
   - 应用会自动创建子目录：
     - `Notes/` - 存放原始 Markdown 文件
     - `Organized/` - 存放整合后的笔记
     - `Raw/` - 存放原始文件（PDF/DOCX 等）
2. **配置 API**
   - 点击侧边栏「设置」图标
   - 输入 OpenAI API Key（或兼容格式的 API）
   - 可选：设置 API Base URL、模型名称、温度等

### 功能使用

#### 网页下载

1. 点击「网页」标签
2. 在文本框中输入 URL（每行一个）
3. 可选：
   - 「AI 辅助」：启用智能排版
   - 「包含图片」：下载网页图片
4. 点击「开始下载」

#### 文件转换

1. 点击「转换」标签
2. 点击「添加文件」或「添加文件夹」
3. 支持格式：PDF、DOCX、PPTX、TXT
4. 可选：启用「AI 辅助」
5. 点击「开始转换」

#### 主题提取与笔记整合

1. 点击「整合」标签
2. 点击「提取主题」：自动分析 Notes 文件夹中的文件
3. 查看生成的主题列表，可手动编辑
4. 点击「开始整合」：按主题生成结构化笔记

#### 文件浏览与编辑

1. 点击「文件」标签
2. 在左侧文件树中点击文件
3. 简单文件直接显示内容
4. Markdown 文件：
   - 点击分栏按钮（关闭按钮左侧）开启双栏模式
   - 左侧：CodeMirror 6 编辑器
   - 右侧：实时预览
   - 修改自动保存

## API 配置

### 支持的 API 提供商

| 提供商          | 配置说明                                  |
| ------------ | ------------------------------------- |
| OpenAI (默认)  | API Base: `https://api.openai.com/v1` |
| Azure OpenAI | 填入对应的 API Base 和部署名称                  |
| 其他兼容格式       | 任何支持 OpenAI API 格式的服务商                |

### 配置参数

| 参数         | 说明          | 默认值                         |
| ---------- | ----------- | --------------------------- |
| API Key    | 您的 API 密钥   | -                           |
| API Base   | API 端点地址    | `https://api.openai.com/v1` |
| 模型名称       | 使用的模型       | `gpt-4`                     |
| 温度         | 输出随机性 (0-1) | `0.7`                       |
| Max Tokens | 最大输出 tokens | `32000`                     |

### 配置存储

配置文件保存在：

- macOS: `~/.config/NoteAI/config.json`
- Windows: `%APPDATA%\NoteAI\config.json`
- Linux: `~/.config/NoteAI/config.json`

## 工作区目录结构

设置工作区后，目录结构如下：

```
工作区/
├── Notes/           # Markdown 文件（下载/转换后）
├── Organized/       # 整合后的笔记（按主题分类）
├── Raw/             # 原始文件（PDF/DOCX/PPTX 等）
└── Used/            # 已处理的文件（整合后自动移动）
```

## 故障排除

### 常见问题

**1. Markdown 编辑器或预览异常**

- 确认使用 `python run.py` 启动的 Tauri 应用
- 查看应用内「日志」或终端侧 Python/Tauri 输出

**2. AI 功能无法使用**

- 检查 API Key 是否正确
- 检查网络连接
- 查看应用内「日志」标签页

**3. 文件转换失败**

- 检查文件是否损坏
- 检查文件权限
- 查看日志了解详细错误

### 日志查看

- 应用内点击「日志」标签页
- 或查看日志文件：`~/.config/NoteAI/logs/`

## 开发说明

### 架构（当前）

- **壳**：Tauri（`src-tauri/`）加载 `webui/` 静态资源。
- **后端**：`python/main.py` 启动 `python/sidecar/server.py` 中的 `SidecarServer`（stdin/stdout JSON）；Rust 通过 `invoke('py_call', { method, params })` 转发。
- **`webui/app.py`**：已删除（历史 HTTP 调试入口，无调用者）。

### 前后端通信

- **JS → Python**：`window.__TAURI__.core.invoke('py_call', { method, params })`（见 `webui/js/api.js`）。
- **Python → JS（进度/事件）**：sidecar 写出 `id: "event"` 的 JSON 行，Rust 转发为前端事件。

### 添加新的 API 方法

1. 在 `python/sidecar/server.py` 的 `handle_request` → `handler_map` 中注册方法名，并在对应 `python/sidecar/mixins/*.py` 中实现 `_方法名(self, params)`。
2. 在 `webui/js/api.js` 增加封装函数并导出到 `window.api`。

## 许可证

MIT License

## 贡献

欢迎提交 Issue 或 Pull Request。
