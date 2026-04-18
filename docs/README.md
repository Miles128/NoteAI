# NoteAI - AI驱动的Markdown笔记知识库管理

## 项目简介

NoteAI是一个功能完善的AI驱动Markdown笔记知识库管理桌面应用，使用Python和Tkinter开发，集成了Langchain实现AI相关功能。

## 核心功能

### 1. 网络文章批量下载与转换模块
- 接收用户输入的一系列网络链接，按顺序执行下载操作
- 将下载的网页内容自动转换为Markdown格式
- 智能识别并删除乱码内容及图片元素
- 应用预设排版规则进行格式优化
- 支持自定义保存路径

### 2. 多格式文件转换模块
- 支持PDF、PPT、DOCX、TXT与Markdown格式的双向转换
- 转换过程中自动执行内容净化
- 集成LLM大模型实现智能排版
- 提供文件保存路径设置选项

### 3. 智能笔记主题整合模块
- 支持文件夹导入功能，批量处理Markdown文件
- 三种整合策略：
  - **基础机器学习分类整合**：使用scikit-learn进行标题分析与主题分类
  - **RAG增强整合**：实现检索增强生成方案
  - **长上下文直接整合**：利用LLM模型的长上下文处理能力

## 技术架构

### 技术栈
- **GUI框架**: Tkinter + CustomTkinter
- **AI框架**: Langchain + Langchain-OpenAI
- **机器学习**: scikit-learn, sentence-transformers
- **向量数据库**: ChromaDB / FAISS
- **文档处理**: BeautifulSoup4, python-docx, PyPDF2, python-pptx

### 项目结构
```
noteai/
├── main.py                 # 应用入口
├── requirements.txt        # 依赖包列表
├── config/                 # 配置模块
│   ├── __init__.py
│   └── settings.py         # 应用配置
├── modules/                # 功能模块
│   ├── __init__.py
│   ├── web_downloader.py   # 网页下载模块
│   ├── file_converter.py   # 文件转换模块
│   └── note_integration.py # 笔记整合模块
├── ui/                     # 界面模块
│   ├── __init__.py
│   ├── main_window.py      # 主窗口
│   └── material_theme.py   # Material Design主题
├── utils/                  # 工具模块
│   ├── __init__.py
│   ├── logger.py           # 日志管理
│   └── helpers.py          # 辅助函数
├── prompts/                # Prompt模板
│   ├── __init__.py
│   ├── web_download.py
│   ├── file_conversion.py
│   └── note_integration.py
├── docs/                   # 文档
│   └── README.md
└── assets/                 # 资源文件
```

## 安装说明

### 环境要求
- Python 3.8+
- Windows 10/11

### 安装步骤

1. 克隆或下载项目
```bash
cd noteai
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 运行应用
```bash
python main.py
```

## 使用指南

### 初始配置
1. 打开应用后，点击"API配置"标签页
2. 输入您的OpenAI API Key（或其他兼容API）
3. 设置API Base URL（可选，默认为OpenAI官方）
4. 选择模型（如gpt-4, gpt-3.5-turbo等）
5. 点击"保存配置"

### 网页下载
1. 切换到"网页下载"标签页
2. 在文本框中输入要下载的URL（每行一个）
3. 设置保存路径
4. 勾选"使用AI优化转换"（推荐）
5. 点击"开始下载"

### 文件转换
1. 切换到"文件转换"标签页
2. 点击"添加文件"或"添加文件夹"选择要转换的文件
3. 支持的格式：PDF、DOCX、PPTX、TXT
4. 设置输出路径
5. 点击"开始转换"

### 笔记整合
1. 切换到"笔记整合"标签页
2. 选择源文件夹（包含Markdown文件）
3. 选择整合策略：
   - **机器学习分类**：可选择自动提取主题或手动指定
   - **RAG增强**：输入查询内容，基于检索生成
   - **长上下文**：直接处理所有文档
4. 设置输出路径
5. 点击"开始整合"

## API配置说明

### 支持的API提供商
- OpenAI (默认)
- Azure OpenAI
- 其他兼容OpenAI API格式的服务商

### 配置示例

**OpenAI:**
- API Key: `sk-...`
- API Base: `https://api.openai.com/v1`
- 模型: `gpt-4` 或 `gpt-3.5-turbo`

**Azure OpenAI:**
- API Key: 您的Azure API Key
- API Base: `https://your-resource.openai.azure.com/`
- 模型: 您的部署名称

## 配置存储

应用配置存储在用户目录下的 `NoteAI/config.json` 文件中：
- Windows: `%USERPROFILE%\NoteAI\config.json`

日志文件存储在：`%USERPROFILE%\NoteAI\logs\`

## 注意事项

1. **API Key安全**: 请勿将API Key提交到代码仓库
2. **网络连接**: 使用AI功能需要稳定的网络连接
3. **Token限制**: 长文档可能会被截断处理
4. **文件编码**: 建议统一使用UTF-8编码

## 故障排除

### 常见问题

1. **启动失败**
   - 检查Python版本（需要3.8+）
   - 检查依赖包是否正确安装

2. **AI功能无法使用**
   - 检查API Key是否正确
   - 检查网络连接
   - 查看日志了解详细错误

3. **转换失败**
   - 检查文件是否损坏
   - 检查文件编码
   - 查看日志了解详细错误

### 日志查看
- 在应用内点击"日志"标签页查看
- 或查看 `%USERPROFILE%\NoteAI\logs\` 目录下的日志文件

## 开发计划

- [ ] 支持更多文件格式（EPUB、HTML等）
- [ ] 添加插件系统
- [ ] 支持本地模型（Llama、ChatGLM等）
- [ ] 添加笔记搜索功能
- [ ] 支持云同步

## 许可证

MIT License

## 联系方式

如有问题或建议，欢迎提交Issue或Pull Request。
