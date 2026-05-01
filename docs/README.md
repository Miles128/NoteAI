# NoteAI - AI驱动的Markdown笔记知识库管理

## 项目简介

<<<<<<< tr35
NoteAI 是一个功能完善的 AI 驱动 Markdown 笔记知识库管理桌面应用。使用**Tauri**作为前端框架，结合 HTML/CSS/JS 构建现代化界面，集成 LangChain 实现 AI 相关功能。
=======
NoteAI是一个功能完善的AI驱动Markdown笔记知识库管理桌面应用，使用Python和Tauri开发，集成了Langchain实现AI相关功能。 核心功能-网络文章批量下载，多格式文件批量转换，智能笔记主题整合。
>>>>>>> main

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

| 类别     | 技术                                            |
| ------ | --------------------------------------------- |
| GUI 框架 | PySide6 (QtWebEngine) / pywebview             |
| 前端界面   | HTML5 + CSS3 + JavaScript                     |
| 代码编辑器  | CodeMirror 6                                  |
| AI 框架  | LangChain + LangChain-OpenAI                  |
| 文档处理   | BeautifulSoup4, python-docx, PyMuPDF, mammoth |
| 包管理    | uv                                            |

### 项目结构

```
NoteAI/
├── main.py                  # 应用入口（自动选择前端框架）
├── requirements.txt         # 依赖包列表
├── config/
│   ├── __init__.py
│   ├── settings.py          # 应用配置管理
│   └── config.json          # 用户配置文件
├── webui/
│   ├── index.html           # 前端界面（单页应用）
│   ├── app_pyside6.py       # PySide6 版本入口
│   ├── app.py               # pywebview 版本入口
│   └── codemirror-bundle.mjs # CodeMirror 6 编辑器（自动下载）
├── modules/
│   ├── __init__.py
│   ├── web_downloader.py    # 网页下载模块
│   ├── file_converter.py    # 文件转换模块
│   ├── note_integration.py  # 笔记整合模块
│   ├── topic_extractor.py   # 主题提取模块
│   └── file_preview.py      # 文件预览模块
├── prompts/
│   ├── __init__.py
│   ├── web_download.py
│   ├── file_conversion.py
│   ├── note_integration.py
│   ├── topic_extraction.py
│   └── unified.py
├── utils/
│   ├── __init__.py
│   ├── helpers.py
│   ├── logger.py
│   └── tag_extractor.py
├── tests/
│   └── ...                  # 测试文件
└── docs/
    ├── README.md
    ├── API.md
    └── USAGE.md
```

## 安装说明

### 环境要求

- Python 3.9+
- macOS / Windows / Linux

### 安装步骤

1. 克隆项目

```bash
git clone https://github.com/Miles128/NoteAI.git
cd NoteAI
```

1. 创建虚拟环境并安装依赖

```bash
# 使用 uv 创建虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# 或 .venv\Scripts\activate  # Windows

# 安装基础依赖
uv pip install -r requirements.txt

# 安装 PySide6（推荐，功能更完整）
uv pip install PySide6
```

> 注意：如果不安装 PySide6，应用会自动使用 pywebview 运行。

### 运行应用

```bash
python main.py
```

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

**1. Markdown 编辑器内容不显示**

- 原因：pywebview 使用 `file://` 协议，不支持 ES Module 动态 `import()`
- 解决：安装 PySide6 (`uv pip install PySide6`)

**2. 打开 MD 文件闪退**

- 原因：同上
- 解决：使用 PySide6 版本

**3. AI 功能无法使用**

- 检查 API Key 是否正确
- 检查网络连接
- 查看应用内「日志」标签页

**4. 文件转换失败**

- 检查文件是否损坏
- 检查文件权限
- 查看日志了解详细错误

### 日志查看

- 应用内点击「日志」标签页
- 或查看日志文件：`~/.config/NoteAI/logs/`

## 开发说明

### 前端框架选择

`main.py` 中的选择逻辑：

```python
# 优先使用 PySide6
if PYSIDE6_AVAILABLE:
    from webui.app_pyside6 import main
    main()
else:
    # 回退到 pywebview
    from webui.app import main
    main()
```

### 前后端通信

通信机制采用 URL 拦截方式，保持 `window.pywebview.api.xxx` 接口兼容：

- **JS → Python**: `noteai://api/method_name?args=[...]`
- **Python → JS**: `window.__noteai_api_result__()` / `window.__noteai_api_error__()`

### 添加新的 API 方法

1. 在 `webui/app_pyside6.py` 和 `webui/app.py` 的 `Api` 类中添加方法
2. 在 `webui/index.html` 的 `api_methods` 数组中添加方法名
3. 前端通过 `window.pywebview.api.method_name(args...)` 调用

## 许可证

MIT License

## 贡献

欢迎提交 Issue 或 Pull Request。
