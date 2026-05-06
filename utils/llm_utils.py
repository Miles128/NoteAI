"""LLM 调用相关的统一工具模块"""

import re
import time
import threading
from typing import Optional, Tuple, Callable

from utils.logger import logger


class APIConfigError(Exception):
    """API配置错误异常"""
    pass


class NetworkError(Exception):
    """网络连接错误异常"""
    pass


class LLMRateLimitError(Exception):
    """LLM 限流错误"""
    pass


# 全局信号量，限制并发 LLM 调用数
_LLM_SEMAPHORE = threading.BoundedSemaphore(4)


def _retry_with_backoff(
    fn: Callable,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
) -> str:
    """带指数退避的重试包装器"""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            with _LLM_SEMAPHORE:
                return fn()
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # 判断是否可重试
            retryable = any(kw in error_str for kw in (
                '429', 'rate limit', 'too many', '503', '502', '504',
                'timeout', 'timed out', 'connection', 'reset', 'overloaded'
            ))
            if not retryable or attempt >= max_retries:
                break
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(f"LLM 调用失败 (尝试 {attempt+1}/{max_retries+1})，"
                           f"{delay:.1f}s 后重试: {e}")
            time.sleep(delay)
    raise last_error  # type: ignore[misc]


def is_network_error(exception: Exception) -> bool:
    """判断异常是否为网络相关错误"""
    error_str = str(exception).lower()
    error_type = type(exception).__name__.lower()

    network_keywords = [
        'timeout', 'timed out', 'connection', 'connect',
        'network', 'socket', 'dns', 'unreachable',
        'refused', 'reset', 'abort', 'closed',
        'ssl', 'certificate', 'handshake',
        'proxy', 'tunnel', 'gateway',
        'httpx', 'urllib3', 'requests'
    ]

    for keyword in network_keywords:
        if keyword in error_str or keyword in error_type:
            return True

    network_exception_types = [
        'timeout', 'connection', 'socket', 'ssl',
        'proxy', 'http', 'url', 'network'
    ]

    for net_type in network_exception_types:
        if net_type in error_type:
            return True

    return False


def _create_llm(temperature: float = 0.7, max_tokens: Optional[int] = None):
    """创建 ChatOpenAI 实例（内部复用）"""
    from langchain_openai import ChatOpenAI
    from config.settings import config

    kwargs = {
        "api_key": config.api_key,
        "base_url": config.api_base,
        "model": config.model_name,
        "temperature": temperature,
        "max_tokens": max_tokens or config.max_tokens,
        "request_timeout": 60,
    }

    if getattr(config, 'disable_thinking', True):
        kwargs["model_kwargs"] = {"extra_body": {"thinking": {"type": "disabled"}}}

    return ChatOpenAI(**kwargs)


def call_llm(
    prompt_template: str,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    **kwargs
) -> str:
    """统一 LLM 调用入口（模板模式），带指数退避重试。无 kwargs 时自动回退到原始文本模式。"""
    if not kwargs:
        return call_llm_raw(prompt_template, temperature, max_tokens)

    from langchain_core.prompts import PromptTemplate

    def _invoke():
        llm = _create_llm(temperature, max_tokens)
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=list(kwargs.keys())
        )
        chain = prompt | llm
        return chain.invoke(kwargs)

    response = _retry_with_backoff(_invoke)
    if hasattr(response, "content"):
        return response.content.strip()
    return str(response).strip()


def call_llm_raw(
    prompt_text: str,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
) -> str:
    """统一 LLM 调用入口（原始文本模式），带指数退避重试。"""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

    def _invoke():
        llm = _create_llm(temperature, max_tokens)
        return llm.invoke(prompt_text)

    def _invoke_with_timeout():
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_invoke)
            try:
                return future.result(timeout=90)
            except FutureTimeout:
                raise RuntimeError("LLM 调用超时（90秒）")

    response = _retry_with_backoff(_invoke_with_timeout)
    if hasattr(response, "content"):
        return response.content.strip()
    return str(response).strip()


def check_api_config() -> Tuple[bool, str]:
    """检查API配置是否完整且可用"""
    from config.settings import config

    if not config.api_key or not config.api_key.strip():
        return False, "API Key 未配置，请先配置 API Key"

    api_key = config.api_key.strip()
    if len(api_key) < 10:
        return False, "API Key 格式无效，请检查配置"

    if not config.api_base or not config.api_base.strip():
        return False, "API Base URL 未配置，请先配置 API Base"

    if not config.model_name or not config.model_name.strip():
        return False, "模型名称未配置，请先配置模型"

    return True, ""


def _classify_api_error(error_msg: str, api_base: str, model_name: str) -> str:
    """分类 API 错误，返回更具体的错误信息"""
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
    """规范化 API Base URL"""
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
    """测试 API 连接是否可用"""
    logger.info(f"[API连接测试] 开始测试连接...")
    logger.info(f"[API连接测试] API Base: {api_base}")
    logger.info(f"[API连接测试] 模型名称: {model_name}")

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

    result = [None]

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


def _estimate_tokens(text: str, model_name: str = "gpt-4") -> int:
    """估算文本的 token 数量"""
    try:
        import tiktoken
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))
    except Exception:
        return len(text) // 4


def summarize_with_llm(content: str, target_ratio: float = 0.5) -> str:
    """使用 LLM 对内容进行智能摘要提取"""
    is_valid, error_msg = check_api_config()
    if not is_valid:
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
        if is_network_error(e):
            logger.error(f"大模型服务网络连接失败: {e}")
            raise NetworkError("大模型服务连接失败，请检查您的网络连接状态后重试")
        logger.error(f"LLM摘要失败: {e}, 返回原始内容")
        return content


def compress_with_llm(content: str, compression_level: str = "medium") -> str:
    """使用 LLM 对内容进行智能压缩"""
    is_valid, error_msg = check_api_config()
    if not is_valid:
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
        if is_network_error(e):
            logger.error(f"大模型服务网络连接失败: {e}")
            raise NetworkError("大模型服务连接失败，请检查您的网络连接状态后重试")
        logger.error(f"LLM压缩失败: {e}, 返回原始内容")
        return content


def process_content_with_llm(content: str, max_tokens: int = 131072, model_name: str = "gpt-4") -> tuple:
    """使用LLM智能处理内容，当超出上下文限制时进行摘要、压缩、截断"""
    estimated_tokens = _estimate_tokens(content, model_name)

    if estimated_tokens <= max_tokens:
        return (content, False, False, estimated_tokens)

    target_ratio = min(0.7, max_tokens / estimated_tokens)
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
    from utils.helpers import smart_truncate_text
    max_chars = int(len(compressed_content) * max_tokens / compressed_tokens)
    truncated_content = smart_truncate_text(
        compressed_content,
        max_length=max_chars,
        suffix="\n\n---\n\n[内容已截断，超出上下文限制。已优先保留核心信息和关键逻辑。]"
    )
    truncated_tokens = _estimate_tokens(truncated_content, model_name)
    logger.info(f"策略性截断完成，最终{truncated_tokens} tokens")
    return (truncated_content, True, True, truncated_tokens)


def rewrite_with_llm(content: str) -> str:
    if not content or not content.strip():
        return content

    is_valid, error_msg = check_api_config()
    if not is_valid:
        raise APIConfigError(error_msg)

    from prompts.llm_rewrite import LLM_REWRITE_PROMPT

    return call_llm(
        LLM_REWRITE_PROMPT,
        temperature=0.3,
        content=content
    )


def rewrite_with_llm_stream(content: str, chunk_callback=None):
    if not content or not content.strip():
        if chunk_callback:
            chunk_callback(content)
        return content

    is_valid, error_msg = check_api_config()
    if not is_valid:
        raise APIConfigError(error_msg)

    from langchain_core.prompts import PromptTemplate
    from prompts.llm_rewrite import LLM_REWRITE_PROMPT

    llm = _create_llm(temperature=0.3)
    prompt = PromptTemplate(
        template=LLM_REWRITE_PROMPT,
        input_variables=["content"]
    )
    chain = prompt | llm

    full_text = ""
    if chunk_callback:
        for chunk in chain.stream({"content": content}):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_text += token
            chunk_callback(token)
    else:
        for chunk in chain.stream({"content": content}):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_text += token

    return full_text.strip()


def reformat_markdown_with_llm(content: str) -> str:
    """使用 LLM 重新格式化 Markdown 内容"""
    if not content or not content.strip():
        return content

    from config.settings import config
    if not config.api_key:
        return content

    try:
        from prompts import MARKDOWN_REFORMAT_PROMPT
        result = call_llm(
            MARKDOWN_REFORMAT_PROMPT,
            temperature=0.2,
            content=content
        )
        if result and result.strip():
            return result
        return content
    except Exception as e:
        import sys
        sys.stderr.write(f"[reformat_markdown_with_llm] LLM formatting failed: {e}\n")
        sys.stderr.flush()
        return content
