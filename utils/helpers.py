import re
import os
import hashlib
from pathlib import Path
from typing import Optional, List, Tuple
import unicodedata

class APIConfigError(Exception):
    """API配置错误异常"""
    pass


class NetworkError(Exception):
    """网络连接错误异常"""
    pass


def is_network_error(exception: Exception) -> bool:
    """
    判断异常是否为网络相关错误
    
    Args:
        exception: 捕获的异常
        
    Returns:
        是否为网络错误
    """
    error_str = str(exception).lower()
    error_type = type(exception).__name__.lower()
    
    # 常见的网络错误关键词
    network_keywords = [
        'timeout', 'timed out', 'connection', 'connect',
        'network', 'socket', 'dns', 'unreachable',
        'refused', 'reset', 'abort', 'closed',
        'ssl', 'certificate', 'handshake',
        'proxy', 'tunnel', 'gateway',
        'httpx', 'urllib3', 'requests'
    ]
    
    # 检查错误消息中是否包含网络相关关键词
    for keyword in network_keywords:
        if keyword in error_str or keyword in error_type:
            return True
    
    # 检查异常类型
    network_exception_types = [
        'timeout', 'connection', 'socket', 'ssl',
        'proxy', 'http', 'url', 'network'
    ]
    
    for net_type in network_exception_types:
        if net_type in error_type:
            return True
    
    return False


def call_llm(
    prompt_template: str,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    **kwargs
) -> str:
    """
    统一 LLM 调用入口。

    参数说明：
        prompt_template: Prompt 模板字符串，包含 {placeholder} 占位符
        temperature: 采样温度，0~1，越高越随机
        max_tokens: 最大输出 token 数，None 则使用 config 默认值
        **kwargs: 模板变量名到值的映射

    返回：
        LLM 输出的文本（已 strip）

    异常：
        NetworkError: 网络不可达时抛出
        Exception: 其他 LLM 调用错误

    使用示例：
        result = call_llm("请总结以下内容：{content}", content="...")
        result = call_llm(MY_PROMPT, temperature=0.3, topic_name="Python", content="...")
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import PromptTemplate
    from langchain_core.exceptions import LangChainException
    from config.settings import config

    llm = ChatOpenAI(
        api_key=config.api_key,
        base_url=config.api_base,
        model=config.model_name,
        temperature=temperature,
        max_tokens=max_tokens or config.max_tokens
    )

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=list(kwargs.keys())
    )

    chain = prompt | llm
    response = chain.invoke(kwargs)

    if hasattr(response, "content"):
        return response.content.strip()
    return str(response).strip()


def check_api_config() -> Tuple[bool, str]:
    """
    检查API配置是否完整且可用
    
    Returns:
        (is_valid, error_message)
    """
    try:
        from config.settings import config
        
        # 检查API Key
        if not config.api_key or not config.api_key.strip():
            return False, "API Key 未配置，请先配置 API Key"
        
        api_key = config.api_key.strip()
        if len(api_key) < 10:
            return False, "API Key 格式无效，请检查配置"
        
        # 检查API Base
        if not config.api_base or not config.api_base.strip():
            return False, "API Base URL 未配置，请先配置 API Base"
        
        # 检查模型名称
        if not config.model_name or not config.model_name.strip():
            return False, "模型名称未配置，请先配置模型"
        
        return True, ""
        
    except Exception as e:
        return False, f"检查API配置时出错: {str(e)}"

def _classify_api_error(error_msg: str, api_base: str, model_name: str) -> str:
    """
    分类 API 错误，返回更具体的错误信息

    参数:
        error_msg: 原始错误消息
        api_base: API 基础 URL
        model_name: 模型名称

    返回:
        分类后的错误信息
    """
    error_str = error_msg.lower()

    if "401" in error_str or "unauthorized" in error_str or "authentication" in error_str:
        if "api key" in error_str or "invalid" in error_str:
            return "API 认证失败：密钥无效或已过期"
        return "API 认证失败，请检查 API Key 是否正确"

    if "403" in error_str or "forbidden" in error_str:
        return "API 访问被拒绝：可能是账户余额不足或权限受限"

    if "404" in error_str or "not found" in error_str:
        if "model" in error_str:
            return f"模型不存在或不可用：{model_name}"
        return f"API 端点不存在，请检查 API Base URL：{api_base}"

    if "429" in error_str or "rate limit" in error_str or "too many" in error_str:
        return "API 请求频率超限，请稍后重试"

    if "500" in error_str or "502" in error_str or "503" in error_str or "504" in error_str:
        return "API 服务器错误，请稍后重试或检查 API 状态"

    if "connection" in error_str or "connect" in error_str:
        if "refused" in error_str:
            return f"无法连接到 API 服务器，连接被拒绝，请检查 API Base URL：{api_base}"
        if "reset" in error_str:
            return "API 连接被重置，请检查网络连接"
        return f"无法连接到 API 服务器，请检查网络和 API 地址：{api_base}"

    if "timeout" in error_str or "timed out" in error_str:
        return f"API 连接超时，请检查网络和 API 地址：{api_base}"

    if "dns" in error_str or "name or service not known" in error_str or "nodename nor servname" in error_str:
        return f"DNS 解析失败，无法解析 API 地址：{api_base}"

    if "ssl" in error_str or "certificate" in error_str:
        return "SSL 证书验证失败，请检查 API 地址是否正确或网络环境"

    if "proxy" in error_str:
        return "代理连接失败，请检查代理配置"

    if "invalid url" in error_str or "malformed" in error_str:
        return f"API Base URL 格式无效：{api_base}"

    if "insufficient_quota" in error_str or "quota" in error_str or "balance" in error_str:
        return "API 配额不足或账户余额不足，请检查账户状态"

    if "context_length" in error_str or "maximum context" in error_str:
        return "请求内容超出模型上下文长度限制"

    return f"API 连接失败：{error_msg}"


def _normalize_api_base(api_base: str) -> str:
    """
    规范化 API Base URL，确保格式正确

    参数:
        api_base: 原始 API Base URL

    返回:
        规范化后的 URL
    """
    if not api_base:
        return "https://api.openai.com/v1"

    api_base = api_base.strip()

    if not api_base.startswith("http://") and not api_base.startswith("https://"):
        api_base = "https://" + api_base

    if not api_base.endswith("/v1") and not api_base.endswith("/v1/"):
        if api_base.endswith("/"):
            api_base = api_base + "v1"
        else:
            api_base = api_base + "/v1"

    return api_base


def test_api_connection(api_key: str, api_base: str, model_name: str) -> Tuple[bool, str]:
    """
    测试 API 连接是否可用

    参数:
        api_key: API密钥
        api_base: API基础URL
        model_name: 模型名称

    返回:
        (is_connected, message)
    """
    import threading
    import re

    if not api_key or not api_key.strip():
        return False, "API Key 为空，请先配置 API Key"
    if len(api_key.strip()) < 10:
        return False, "API Key 格式无效，请检查配置"

    api_key = api_key.strip()
    api_base = api_base.strip() if api_base else "https://api.openai.com/v1"
    model_name = model_name.strip() if model_name else "gpt-4"

    url_pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )

    if not url_pattern.match(api_base):
        return False, f"API Base URL 格式无效：{api_base}"

    result = [None, None]

    def _test():
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                api_key=api_key,
                base_url=api_base,
                model=model_name,
                temperature=0,
                max_tokens=10
            )
            response = llm.invoke("Hi")
            if response and hasattr(response, "content"):
                result[0] = (True, "API 连接成功")
            else:
                result[0] = (False, "API 响应格式异常")
        except Exception as e:
            result[0] = (False, str(e))

    thread = threading.Thread(target=_test)
    thread.daemon = True
    thread.start()
    thread.join(timeout=15)

    if thread.is_alive():
        return False, f"API 连接超时（15秒），请检查 API 地址：{api_base}"

    if result[0]:
        is_connected, msg = result[0]
        if not is_connected:
            detailed_msg = _classify_api_error(msg, api_base, model_name)
            return False, detailed_msg
        return is_connected, msg

    return False, "未知错误"

def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """清理文件名，移除非法字符"""
    # 移除或替换非法字符
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 移除控制字符
    filename = ''.join(char for char in filename if unicodedata.category(char)[0] != 'C')
    # 限制长度
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    # 移除首尾空格和点
    filename = filename.strip(' .')
    return filename or "unnamed"

def generate_hash(content: str, length: int = 8) -> str:
    """生成内容哈希"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:length]

def clean_text(text: str) -> str:
    """清理文本内容"""
    # 移除乱码字符
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    # 保留换行符，只规范化同一行内的空白
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # 移除零宽字符
        line = re.sub(r'[\u200b-\u200f\ufeff]', '', line)
        # 规范化同一行内的空白
        line = re.sub(r'[ \t]+', ' ', line)
        cleaned_lines.append(line.strip())
    # 重新连接，保留换行
    text = '\n'.join(cleaned_lines)
    # 移除多余的空行（最多保留一个空行）
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    return text.strip()

def remove_images_from_markdown(md_content: str) -> str:
    """从Markdown中移除图片"""
    # 移除Markdown图片语法 ![alt](url)
    md_content = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', md_content)
    # 移除HTML img标签
    md_content = re.sub(r'<img[^>]+>', '', md_content, flags=re.IGNORECASE)
    # 移除图片引用链接
    md_content = re.sub(r'\[([^\]]+)\]:\s*\S+\.(?:png|jpg|jpeg|gif|webp|svg)\s*\n?', '', md_content, flags=re.IGNORECASE)
    return md_content

def extract_title_from_markdown(md_content: str) -> Optional[str]:
    """从Markdown内容中提取标题"""
    lines = md_content.split('\n')
    for line in lines:
        line = line.strip()
        # 查找一级标题
        if line.startswith('# '):
            return line[2:].strip()
        # 查找二级标题
        if line.startswith('## '):
            return line[3:].strip()
    return None

def split_text_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """将文本分割成块"""
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = min(start + chunk_size, text_length)
        # 尝试在句子边界处分割
        if end < text_length:
            # 查找最近的句子结束符
            for i in range(end, start, -1):
                if text[i-1] in '.。!！?？\n':
                    end = i
                    break
        
        chunks.append(text[start:end].strip())
        start = end - overlap
    
    return chunks

def recursive_markdown_chunk(text: str, chunk_size: int = 1000, overlap: int = 200, current_heading: str = "") -> List[str]:
    """
    递归Markdown切片：按照标题层级、标点符号层层切片
    
    Args:
        text: 待切分的Markdown文本
        chunk_size: 目标切片大小（字符数）
        overlap: 切片重叠字符数
        current_heading: 当前继承的标题前缀
    
    Returns:
        切分后的文本块列表
    """
    if len(text) <= chunk_size:
        if current_heading and not text.startswith('#'):
            return [f"{current_heading}\n\n{text}"]
        return [text]
    
    chunks = []
    
    # 第一层：按Markdown标题分割
    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    headings = list(heading_pattern.finditer(text))
    
    if len(headings) > 1:
        # 有标题结构，按标题分割
        for i in range(len(headings)):
            start_pos = headings[i].start()
            end_pos = headings[i+1].start() if i + 1 < len(headings) else len(text)
            
            section = text[start_pos:end_pos].strip()
            heading_line = headings[i].group(0)
            section_content = text[headings[i].end():end_pos].strip()
            
            # 如果该节仍然太大，递归处理内容
            if len(section) > chunk_size:
                sub_chunks = recursive_markdown_chunk(
                    section_content, 
                    chunk_size, 
                    overlap,
                    current_heading=heading_line
                )
                chunks.extend(sub_chunks)
            else:
                if current_heading:
                    if not section.startswith('#'):
                        section = f"{current_heading}\n\n{section}"
                    else:
                        section = f"{current_heading}\n{section}"
                chunks.append(section)
    elif len(headings) == 1:
        # 只有一个标题，提取标题并处理内容
        heading_line = headings[0].group(0)
        content_after_heading = text[headings[0].end():].strip()
        
        if len(content_after_heading) <= chunk_size:
            full_section = f"{heading_line}\n\n{content_after_heading}"
            if current_heading:
                full_section = f"{current_heading}\n{full_section}"
            chunks.append(full_section)
        else:
            # 内容太大，需要递归处理
            sub_chunks = recursive_markdown_chunk(
                content_after_heading,
                chunk_size,
                overlap,
                current_heading=heading_line
            )
            chunks.extend(sub_chunks)
    else:
        # 没有标题，按段落分割
        paragraphs = re.split(r'\n\n+', text)
        
        if len(paragraphs) > 1 and any(len(p) > chunk_size for p in paragraphs):
            # 有大段落，需要进一步分割
            current_chunk = ""
            for para in paragraphs:
                if len(current_chunk) + len(para) + 2 > chunk_size:
                    if current_chunk:
                        if current_heading and not current_chunk.startswith('#'):
                            current_chunk = f"{current_heading}\n\n{current_chunk}"
                        chunks.append(current_chunk.strip())
                    
                    # 如果单个段落就超过chunk_size，进入第三层
                    if len(para) > chunk_size:
                        sub_chunks = _split_by_punctuation(para, chunk_size, overlap, current_heading)
                        chunks.extend(sub_chunks)
                        current_chunk = ""
                    else:
                        current_chunk = para
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + para
                    else:
                        current_chunk = para
            
            if current_chunk:
                if current_heading and not current_chunk.startswith('#'):
                    current_chunk = f"{current_heading}\n\n{current_chunk}"
                chunks.append(current_chunk.strip())
        else:
            # 第三层：按标点符号分割
            sub_chunks = _split_by_punctuation(text, chunk_size, overlap, current_heading)
            chunks.extend(sub_chunks)
    
    return chunks

def _split_by_punctuation(text: str, chunk_size: int, overlap: int, current_heading: str = "") -> List[str]:
    """
    按标点符号分割文本（递归切片的最后一层）
    
    Args:
        text: 待分割文本
        chunk_size: 目标切片大小
        overlap: 重叠字符数
        current_heading: 当前标题前缀
    
    Returns:
        分割后的文本块列表
    """
    if len(text) <= chunk_size:
        if current_heading and not text.startswith('#'):
            return [f"{current_heading}\n\n{text}"]
        return [text]
    
    chunks = []
    
    # 定义分割优先级：句号 > 分号 > 逗号 > 换行
    punctuation_patterns = [
        r'[.。!！?？]',  # 句子结束符
        r'[;；]',        # 分号
        r'[，,]',        # 逗号
        r'\n',           # 换行
    ]
    
    # 尝试找到最佳分割点
    split_pos = None
    for pattern in punctuation_patterns:
        matches = list(re.finditer(pattern, text))
        if matches:
            # 从chunk_size位置往前找最近的标点
            target_pos = chunk_size
            for match in reversed(matches):
                if match.end() <= target_pos:
                    split_pos = match.end()
                    break
            if split_pos:
                break
    
    # 如果没找到标点，强制在chunk_size处分割
    if split_pos is None:
        split_pos = min(chunk_size, len(text))
    
    chunk = text[:split_pos].strip()
    if current_heading and not chunk.startswith('#'):
        chunk = f"{current_heading}\n\n{chunk}"
    chunks.append(chunk)
    
    # 递归处理剩余部分（确保有进展，避免无限递归）
    remaining_start = split_pos - overlap
    if remaining_start >= split_pos:
        remaining_start = split_pos
    
    remaining = text[remaining_start:].strip()
    
    if remaining and len(remaining) < len(text):
        sub_chunks = _split_by_punctuation(remaining, chunk_size, overlap, current_heading)
        chunks.extend(sub_chunks)
    
    return chunks

def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

def ensure_dir(path: str) -> Path:
    """确保目录存在"""
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj

def is_valid_url(url: str) -> bool:
    """验证URL是否有效"""
    try:
        import validators
        return validators.url(url) is True
    except ImportError:
        import re
        pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return bool(pattern.match(url))

def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def get_file_extension(filename: str) -> str:
    """获取文件扩展名"""
    return Path(filename).suffix.lower()

def read_file_with_encoding(file_path: str, encodings: List[str] = None) -> str:
    """尝试多种编码读取文件"""
    if encodings is None:
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    
    raise RuntimeError(f"无法使用任何编码读取文件: {file_path}")

def validate_api_key(api_key: str) -> bool:
    """验证 API Key 是否有效"""
    if not api_key or not api_key.strip():
        return False
    api_key = api_key.strip()
    if len(api_key) < 10:
        return False
    return True

def detect_language(text: str) -> str:
    """简单检测文本语言"""
    if not text:
        return 'unknown'
    chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
    total_chars = len(text)
    if total_chars == 0:
        return 'unknown'
    chinese_ratio = chinese_chars / total_chars
    if chinese_ratio > 0.3:
        return 'chinese'
    return 'english'

def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    import time
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator

def summarize_with_llm(content: str, target_ratio: float = 0.5) -> str:
    """
    使用 LLM 对内容进行智能摘要提取。

    参数：
        content: 原始内容
        target_ratio: 目标压缩比例（0~1），默认 0.5 表示压缩到原来的一半

    返回：
        摘要后的内容

    说明：
        内部调用统一的 call_llm 入口，复用 ChatOpenAI 实例化和 PromptTemplate 构建逻辑。
        当 API 不可用或调用失败时，返回原始内容。
    """
    is_valid, error_msg = check_api_config()
    if not is_valid:
        from utils.logger import logger
        logger.error(f"API配置检查失败: {error_msg}")
        return content

    from prompts.note_integration import CONTENT_SUMMARIZE_PROMPT

    try:
        return call_llm(
            CONTENT_SUMMARIZE_PROMPT,
            temperature=0.3,
            content=content,
            target_ratio=target_ratio
        )
    except NetworkError:
        raise
    except Exception as e:
        from utils.logger import logger
        if is_network_error(e):
            logger.error(f"大模型服务网络连接失败: {e}")
            raise NetworkError("大模型服务连接失败，请检查您的网络连接状态后重试")
        logger.error(f"LLM摘要失败: {e}, 返回原始内容")
        return content


def compress_with_llm(content: str, compression_level: str = "medium") -> str:
    """
    使用 LLM 对内容进行智能压缩，保留核心信息、关键逻辑和重要数据。

    参数：
        content: 原始内容
        compression_level: 压缩级别 ("light" | "medium" | "heavy")

    返回：
        压缩后的内容

    说明：
        内部调用统一的 call_llm 入口，复用 ChatOpenAI 实例化和 PromptTemplate 构建逻辑。
        当 API 不可用或调用失败时，返回原始内容。
    """
    is_valid, error_msg = check_api_config()
    if not is_valid:
        from utils.logger import logger
        logger.error(f"API配置检查失败: {error_msg}")
        return content

    from prompts.note_integration import CONTENT_COMPRESS_PROMPT

    try:
        return call_llm(
            CONTENT_COMPRESS_PROMPT,
            temperature=0.2,
            content=content,
            compression_level=compression_level
        )
    except NetworkError:
        raise
    except Exception as e:
        from utils.logger import logger
        if is_network_error(e):
            logger.error(f"大模型服务网络连接失败: {e}")
            raise NetworkError("大模型服务连接失败，请检查您的网络连接状态后重试")
        logger.error(f"LLM压缩失败: {e}, 返回原始内容")
        return content


def extract_pdf_text(file_path: str, strip: bool = True) -> str:
    """
    使用 PyMuPDF（fitz）从 PDF 文件中提取全部文本，并以页为单位用双换行拼接。

    参数：
        file_path: PDF 文件路径
        strip: 是否对每页文本执行 strip()，默认 True

    返回：
        所有页面文本拼接后的字符串

    说明：
        统一了 file_converter 和 file_preview 中各自独立实现的 PDF 文本提取逻辑。
        该函数不处理任何签名/页眉/页脚移除，仅负责提取。
    """
    import fitz

    doc = fitz.open(file_path)
    parts = []
    for page in doc:
        text = page.get_text("text")
        parts.append(text.strip() if strip else text)
    doc.close()
    return "\n\n".join(parts)


def extract_pdf_pages(file_path: str) -> List[str]:
    """
    使用 PyMuPDF（fitz）从 PDF 文件中逐页提取文本。

    参数：
        file_path: PDF 文件路径

    返回：
        每页文本的列表，顺序与页码一致，每条文本已 strip()

    说明：
        用于需要按页处理的场景，如签名/页眉/页脚检测（file_converter 中签名检测逻辑）。
    """
    import fitz

    doc = fitz.open(file_path)
    texts = [page.get_text("text").strip() for page in doc]
    doc.close()
    return texts


def smart_truncate_text(text: str, max_length: int = 1000, suffix: str = "...") -> str:
    """
    智能截断文本，遵循重要信息优先保留原则
    
    策略：
    1. 保留标题和标题层级结构
    2. 保留开头部分（通常包含核心信息）
    3. 在段落边界截断
    4. 在句子边界截断
    5. 添加明确的截断标记
    
    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀
    
    Returns:
        截断后的文本
    """
    if len(text) <= max_length:
        return text
    
    available_length = max_length - len(suffix)
    
    lines = text.split('\n')
    result_lines = []
    current_length = 0
    found_content_start = False
    
    for line in lines:
        line_length = len(line) + 1
        
        if line.strip().startswith('#'):
            result_lines.append(line)
            current_length += line_length
            found_content_start = True
        elif not found_content_start and line.strip() == '':
            result_lines.append(line)
            current_length += line_length
        else:
            if current_length + line_length <= available_length:
                result_lines.append(line)
                current_length += line_length
                found_content_start = True
            else:
                remaining = available_length - current_length
                if remaining > 50:
                    truncated_line = _truncate_at_sentence_boundary(line, remaining)
                    result_lines.append(truncated_line)
                break
    
    result = '\n'.join(result_lines)
    
    if len(result) > max_length:
        result = result[:available_length]
    
    result = result.rstrip() + suffix
    
    return result

def _truncate_at_sentence_boundary(text: str, max_length: int) -> str:
    """
    在句子边界处截断文本
    
    Args:
        text: 文本
        max_length: 最大长度
    
    Returns:
        截断后的文本
    """
    if len(text) <= max_length:
        return text
    
    boundary_chars = ['.', '。', '!', '！', '?', '？', '\n']
    
    best_pos = max_length
    for i in range(max_length, 0, -1):
        if text[i-1] in boundary_chars:
            best_pos = i
            break
    
    return text[:best_pos]

def _estimate_tokens(text: str, model_name: str = "gpt-4") -> int:
    try:
        import tiktoken
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))
    except Exception:
        return len(text) // 4

def process_content_with_llm(content: str, max_tokens: int = 131072, model_name: str = "gpt-4") -> tuple:
    """
    使用LLM智能处理内容，当超出上下文限制时：
    1. 首先使用LLM进行摘要提取和智能压缩
    2. 若仍不满足，再进行有策略的内容截断
    
    Args:
        content: 原始内容
        max_tokens: 最大token数限制
        model_name: 模型名称
    
    Returns:
        (processed_content, was_summarized, was_truncated, estimated_tokens)
    """
    estimated_tokens = _estimate_tokens(content, model_name)
    
    if estimated_tokens <= max_tokens:
        return (content, False, False, estimated_tokens)
    
    target_ratio = min(0.7, max_tokens / estimated_tokens)
    
    from utils.logger import logger
    logger.info(f"内容超出限制({estimated_tokens} > {max_tokens} tokens)，开始LLM摘要和压缩")
    
    summarized_content = summarize_with_llm(content, target_ratio)
    
    summarized_tokens = _estimate_tokens(summarized_content, model_name)
    
    if summarized_tokens <= max_tokens:
        logger.info(f"LLM摘要成功，压缩至{summarized_tokens} tokens")
        return (summarized_content, True, False, summarized_tokens)
    
    logger.info(f"LLM摘要后仍超出限制({summarized_tokens} > {max_tokens} tokens)，进行智能压缩")
    
    compressed_content = compress_with_llm(summarized_content, "heavy")
    
    compressed_tokens = _estimate_tokens(compressed_content, model_name)
    
    if compressed_tokens <= max_tokens:
        logger.info(f"LLM压缩成功，压缩至{compressed_tokens} tokens")
        return (compressed_content, True, False, compressed_tokens)
    
    logger.info(f"LLM压缩后仍超出限制({compressed_tokens} > {max_tokens} tokens)，进行策略性截断")
    
    max_chars = int(len(compressed_content) * max_tokens / compressed_tokens)
    truncated_content = smart_truncate_text(
        compressed_content,
        max_length=max_chars,
        suffix="\n\n---\n\n[内容已截断，超出上下文限制。已优先保留核心信息和关键逻辑。]"
    )
    
    truncated_tokens = _estimate_tokens(truncated_content, model_name)
    
    logger.info(f"策略性截断完成，最终{truncated_tokens} tokens")
    return (truncated_content, True, True, truncated_tokens)

def clean_markdown_content(content: str) -> str:
    """
    清理 Markdown 内容，移除乱码、冗余格式

    处理：
    1. 移除零宽字符和控制字符
    2. 规范化标题层级（确保从 # 开始）
    3. 修复多余空行
    4. 规范化列表标记
    5. 清理冗余格式符号
    """
    if not content:
        return content

    lines = content.split('\n')
    cleaned_lines = []
    prev_line_empty = False

    for line in lines:
        line = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', line)
        line = re.sub(r'[\u200b-\u200f\ufeff]', '', line)

        is_empty = not line.strip()

        if is_empty:
            if not prev_line_empty:
                cleaned_lines.append('')
                prev_line_empty = True
            continue

        line = re.sub(r'[ \t]+', ' ', line)
        line = line.rstrip()

        cleaned_lines.append(line)
        prev_line_empty = False

    result = '\n'.join(cleaned_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()

def optimize_markdown_format(content: str, title: str = "") -> str:
    """
    优化 Markdown 格式

    处理：
    1. 确保有一级标题（添加标题或提升现有标题）
    2. 规范化标题层级（# ## ### 顺序）
    3. 规范化列表格式（统一使用 - ）
    4. 中英文之间添加空格（简单处理）
    5. 规范化代码块标记
    """
    if not content:
        return content

    content = clean_markdown_content(content)

    lines = content.split('\n')
    result_lines = []
    found_h1 = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith('#'):
            heading_match = re.match(r'^(#{1,6})\s+(.*)$', stripped)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                if level == 1:
                    found_h1 = True
                result_lines.append(f"{'#' * level} {text}")
                continue

        if stripped.startswith('- ') or stripped.startswith('* '):
            result_lines.append('- ' + stripped[2:])
            continue

        if re.match(r'^\d+\.\s', stripped):
            result_lines.append(stripped)
            continue

        if stripped.startswith('```'):
            lang_match = re.match(r'^```(\w*)$', stripped)
            if lang_match:
                lang = lang_match.group(1)
                if not lang:
                    result_lines.append('```')
                else:
                    result_lines.append(stripped)
            else:
                result_lines.append(stripped)
            continue

        result_lines.append(line)

    result = '\n'.join(result_lines)

    if not found_h1 and title:
        if result.strip():
            result = f"# {title}\n\n{result}"

    return result
