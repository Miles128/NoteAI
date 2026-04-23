# NoteAI API 文档

## 模块说明

### web_downloader.py

#### WebDownloader 类

网页下载器，用于批量下载网络文章并转换为Markdown。

##### 构造函数

```python
WebDownloader(progress_callback: Optional[Callable] = None)
```

**参数**：
- `progress_callback`: 进度回调函数，接收(current, total, message)参数

##### 方法

###### download_article

```python
def download_article(self, url: str, use_ai: bool = True) -> Dict
```

下载单篇文章。

**参数**：
- `url`: 文章URL
- `use_ai`: 是否使用AI优化

**返回**：
```python
{
    'url': str,           # 原始URL
    'success': bool,      # 是否成功
    'title': str,         # 文章标题
    'content': str,       # Markdown内容
    'error': str,         # 错误信息（如有）
    'file_path': str      # 保存路径（如有）
}
```

###### download_batch

```python
def download_batch(
    self, 
    urls: List[str], 
    save_path: str,
    use_ai: bool = True
) -> List[Dict]
```

批量下载文章。

**参数**：
- `urls`: URL列表
- `save_path`: 保存目录
- `use_ai`: 是否使用AI优化

**返回**：结果字典列表

### file_converter.py

#### FileConverterManager 类

文件转换管理器，支持多种格式转换为Markdown。

##### 构造函数

```python
FileConverterManager(progress_callback: Optional[Callable] = None)
```

##### 方法

###### convert_file

```python
def convert_file(
    self, 
    file_path: str, 
    output_path: str,
    output_format: str = 'markdown'
) -> Dict
```

转换单个文件。

**参数**：
- `file_path`: 输入文件路径
- `output_path`: 输出目录
- `output_format`: 输出格式（目前仅支持'markdown'）

**返回**：
```python
{
    'file_path': str,     # 原始文件路径
    'success': bool,      # 是否成功
    'output_path': str,   # 输出文件路径
    'error': str          # 错误信息（如有）
}
```

###### convert_batch

```python
def convert_batch(
    self,
    file_paths: List[str],
    output_path: str,
    output_format: str = 'markdown'
) -> List[Dict]
```

批量转换文件。

###### convert_folder

```python
def convert_folder(
    self,
    folder_path: str,
    output_path: str,
    output_format: str = 'markdown',
    recursive: bool = True
) -> List[Dict]
```

转换整个文件夹。

**参数**：
- `folder_path`: 输入文件夹路径
- `output_path`: 输出目录
- `output_format`: 输出格式
- `recursive`: 是否递归处理子文件夹

##### 支持的格式

```python
FileConverterManager.get_supported_formats() -> List[str]
# 返回: ['.pdf', '.docx', '.pptx', '.txt']
```

### note_integration.py

#### NoteIntegration 类

笔记整合器，提供多种文档整合策略。

##### 构造函数

```python
NoteIntegration(progress_callback: Optional[Callable] = None)
```

##### 方法

###### load_documents_from_folder

```python
def load_documents_from_folder(self, folder_path: str) -> List[Dict]
```

从文件夹加载Markdown文档。

**返回**：
```python
[
    {
        'path': str,       # 文件路径
        'title': str,      # 文档标题
        'content': str,    # 文档内容
        'filename': str    # 文件名
    },
    ...
]
```

###### integrate_with_ml_classification

```python
def integrate_with_ml_classification(
    self,
    documents: List[Dict],
    topics: Optional[List[str]] = None,
    save_path: str = None
) -> List[Dict]
```

使用机器学习分类整合。

**参数**：
- `documents`: 文档列表
- `topics`: 主题列表（None则自动提取）
- `save_path`: 保存路径

**返回**：
```python
[
    {
        'topic': str,           # 主题名称
        'documents': List[Dict], # 该主题下的文档
        'content': str,         # 整合后的内容
        'file_path': str        # 保存路径（如有）
    },
    ...
]
```

###### setup_rag

```python
def setup_rag(self, documents: List[Dict] = None)
```

设置RAG向量数据库。

**注意**：调用此方法前需要确保已安装sentence-transformers

###### integrate_with_rag

```python
def integrate_with_rag(
    self,
    query: str,
    save_path: str = None
) -> Dict
```

使用RAG整合。

**参数**：
- `query`: 查询内容
- `save_path`: 保存路径

**返回**：
```python
{
    'query': str,           # 查询内容
    'content': str,         # 整合后的内容
    'sources': List[Dict],  # 参考来源
    'file_path': str        # 保存路径（如有）
}
```

###### integrate_with_long_context

```python
def integrate_with_long_context(
    self,
    documents: List[Dict],
    save_path: str = None
) -> Dict
```

使用长上下文直接整合。

**返回**：
```python
{
    'content': str,         # 整合后的内容
    'document_count': int,  # 文档数量
    'file_path': str        # 保存路径（如有）
}
```

## 配置类

### AppConfig

应用配置类，用于管理应用设置。

#### 属性

```python
@dataclass
class AppConfig:
    api_key: str                    # API密钥
    api_base: str                   # API基础URL
    model_name: str                 # 模型名称
    temperature: float              # 温度参数
    max_tokens: int                 # 最大令牌数
    log_path: str                   # 日志路径
    batch_size: int                 # 批处理大小
    timeout: int                    # 超时时间
    max_retries: int                # 最大重试次数
    vector_db_path: str             # 向量数据库路径
    chunk_size: int                 # 文本块大小
    chunk_overlap: int              # 文本块重叠大小
    embedding_model: str            # 嵌入模型名称
    theme: str                      # 界面主题
    accent_color: str               # 强调色
    window_width: int               # 窗口宽度
    window_height: int              # 窗口高度
```

#### 方法

```python
# 从文件加载配置
@classmethod
def load_from_file(cls, config_path: str = None) -> 'AppConfig'

# 保存配置到文件
def save_to_file(self, config_path: str = None)

# 转换为字典
def to_dict(self) -> Dict[str, Any]
```

#### 使用示例

```python
from config.settings import config, AppConfig

# 读取配置
print(config.api_key)
print(config.model_name)

# 修改配置
config.api_key = "new-api-key"
config.model_name = "gpt-4"

# 保存配置
config.save_to_file()

# 创建新配置
new_config = AppConfig(
    api_key="sk-...",
    model_name="gpt-3.5-turbo",
    temperature=0.5
)
new_config.save_to_file("/path/to/config.json")
```

## 工具函数

### helpers.py

#### 文件和路径

```python
# 清理文件名
def sanitize_filename(filename: str, max_length: int = 100) -> str

# 确保目录存在
def ensure_dir(path: str) -> Path

# 获取文件扩展名
def get_file_extension(filename: str) -> str

# 格式化文件大小
def format_file_size(size_bytes: int) -> str
```

#### 文本处理

```python
# 清理文本
def clean_text(text: str) -> str

# 从Markdown移除图片
def remove_images_from_markdown(md_content: str) -> str

# 从Markdown提取标题
def extract_title_from_markdown(md_content: str) -> Optional[str]

# 分割文本为块
def split_text_into_chunks(
    text: str, 
    chunk_size: int = 1000, 
    overlap: int = 200
) -> List[str]

# 截断文本
def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str
```

#### 验证和检查

```python
# 验证URL
def is_valid_url(url: str) -> bool

# 生成内容哈希
def generate_hash(content: str, length: int = 8) -> str
```

### logger.py

#### AppLogger 类

```python
# 获取全局日志实例
from utils.logger import logger

# 记录日志
logger.debug("调试信息")
logger.info("普通信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")

# 获取最近的日志
logs = logger.get_logs(lines=100)
```

## 使用示例

### 完整工作流示例

```python
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from modules.web_downloader import WebDownloader
from modules.file_converter import FileConverterManager
from modules.note_integration import NoteIntegration
from config.settings import config

# 配置API
config.api_key = "your-api-key"
config.save_to_file()

# 1. 下载网页文章
def web_download_example():
    urls = [
        "https://example.com/article1",
        "https://example.com/article2"
    ]
    
    downloader = WebDownloader()
    results = downloader.download_batch(
        urls=urls,
        save_path="./downloads",
        use_ai=True
    )
    
    for result in results:
        if result['success']:
            print(f"✓ {result['title']}")
        else:
            print(f"✗ {result['url']}: {result['error']}")

# 2. 转换文件
def file_conversion_example():
    converter = FileConverterManager()
    
    # 转换单个文件
    result = converter.convert_file(
        file_path="document.pdf",
        output_path="./converted"
    )
    
    # 批量转换
    results = converter.convert_batch(
        file_paths=["doc1.pdf", "doc2.docx"],
        output_path="./converted"
    )
    
    # 转换整个文件夹
    results = converter.convert_folder(
        folder_path="./documents",
        output_path="./converted",
        recursive=True
    )

# 3. 整合笔记
def note_integration_example():
    integrator = NoteIntegration()
    
    # 加载文档
    documents = integrator.load_documents_from_folder("./notes")
    
    # 方式1：机器学习分类整合
    results = integrator.integrate_with_ml_classification(
        documents=documents,
        topics=["技术", "管理", "生活"],  # 或None自动提取
        save_path="./integrated"
    )
    
    # 方式2：RAG整合
    integrator.setup_rag(documents)
    result = integrator.integrate_with_rag(
        query="人工智能的发展趋势",
        save_path="./integrated"
    )
    
    # 方式3：长上下文整合
    result = integrator.integrate_with_long_context(
        documents=documents,
        save_path="./integrated"
    )

if __name__ == "__main__":
    # web_download_example()
    # file_conversion_example()
    # note_integration_example()
    pass
```

## 错误处理

所有模块都可能抛出以下异常：

- `ValueError`: 参数错误
- `FileNotFoundError`: 文件不存在
- `PermissionError`: 权限不足
- `requests.RequestException`: 网络请求错误
- `Exception`: 其他未预料的错误

建议使用try-except块处理：

```python
try:
    result = downloader.download_article(url)
except Exception as e:
    print(f"错误: {e}")
    logger.error(f"下载失败: {e}")
```
