import os
import sys
import re
import math
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import hashlib

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import config
from utils.logger import logger


class AgentRole(Enum):
    """
    多智能体框架中各角色的类型枚举。

    未使用说明：
        当前 agents/ 模块链（base.py、context_manager.py、semantic_chunker.py、
        multi_agent_framework.py）定义了一套完整的多智能体工作流框架，包含
        COORDINATOR、EXTRACTOR、SUMMARIZER、INTEGRATOR、REWRITER 五种角色。
        该框架目前没有任何调用方，处于保留状态。
        如未来需要实现"多智能体协作式笔记整合"，可直接启用此模块。
    """
    COORDINATOR = "coordinator"
    EXTRACTOR = "extractor"
    SUMMARIZER = "summarizer"
    INTEGRATOR = "integrator"
    REWRITER = "rewriter"


class TaskStatus(Enum):
    """
    任务执行状态枚举。

    未使用说明：随 AgentRole 配套定义，当前无调用方。
    """
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Chunk:
    """
    文档切分后的文本块数据结构。

    属性：
        id: 块的唯一标识符
        content: 块内的原始文本
        title: 块所属的标题（可选）
        token_count: 该块的 token 估算数（由 estimate_tokens() 自动计算）
        semantic_score: 语义相关性评分（0~1，供排序使用）
        chunk_type: 块类型，默认 "general"
        metadata: 附加元数据字典（如来源文件、页码等）
        previous_chunk_id: 前一个块的 ID（用于链式处理）
        next_chunk_id: 后一个块的 ID（用于链式处理）

    未使用说明：
        被 agents/semantic_chunker.py 中的 SemanticChunker 使用，
        但 semantic_chunker.py 本身也未被调用，故为保留状态。
    """
    id: str
    content: str
    title: str = ""
    token_count: int = 0
    semantic_score: float = 0.0
    chunk_type: str = "general"
    metadata: Dict = field(default_factory=dict)
    previous_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None

    def __post_init__(self):
        if not self.token_count:
            self.token_count = self.estimate_tokens()

    def estimate_tokens(self) -> int:
        """
        估算块内的 token 数量。

        采用中英文混合估算规则：
        - 中文字符：每个字符计 1.5 token（基于 GPT 词表统计）
        - 英文字符：每个单词计 0.25 token
        - 其他字符：每个字符计 0.5 token
        """
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', self.content))
        english_words = len(re.findall(r'[a-zA-Z]+', self.content))
        other = len(self.content) - chinese_chars - english_words
        return int(chinese_chars * 1.5 + english_words * 0.25 + other * 0.5)


@dataclass
class AgentTask:
    """
    智能体任务的数据结构。

    属性：
        task_id: 任务唯一标识
        role: 任务角色类型（AgentRole）
        chunk_ids: 任务关联的文档块 ID 列表
        instruction: 给智能体的具体指令
        status: 当前任务状态（TaskStatus）
        result: 任务执行结果（字典，由具体角色填充）
        error: 任务失败时的错误信息
        created_at: 创建时间戳
        completed_at: 完成时间戳

    未使用说明：随 agents 模块整体保留，当前无调用方。
    """
    task_id: str
    role: AgentRole
    chunk_ids: List[str]
    instruction: str
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict] = None
    error: Optional[str] = None
    created_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> Dict:
        """将任务对象转换为字典（用于序列化）"""
        return {
            "task_id": self.task_id,
            "role": self.role.value,
            "chunk_ids": self.chunk_ids,
            "instruction": self.instruction,
            "status": self.status.value,
            "result": self.result,
            "error": self.error
        }


@dataclass
class ProcessingResult:
    """
    多智能体框架处理结果的汇总数据结构。

    属性：
        original_doc_count: 原始输入文档数量
        total_chunks: 切分后的总块数
        chunks_processed: 实际处理的块数
        agent_tasks: 所有 AgentTask 实例列表
        final_content: 最终整合输出的文本
        section_results: 各章节/主题的独立输出结果
        token_spent: 本次处理消耗的 token 总数
        processing_time: 总处理时长（秒）
        errors: 处理过程中的错误列表

    未使用说明：随 agents 模块整体保留，当前无调用方。
    """
    original_doc_count: int = 0
    total_chunks: int = 0
    chunks_processed: int = 0
    agent_tasks: List[AgentTask] = field(default_factory=list)
    final_content: str = ""
    section_results: Dict[str, str] = field(default_factory=dict)
    token_spent: int = 0
    processing_time: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """将结果对象转换为字典（用于序列化）"""
        return {
            "original_doc_count": self.original_doc_count,
            "total_chunks": self.total_chunks,
            "chunks_processed": self.chunks_processed,
            "agent_tasks": [t.to_dict() for t in self.agent_tasks],
            "final_content": self.final_content,
            "section_results": self.section_results,
            "token_spent": self.token_spent,
            "processing_time": self.processing_time,
            "errors": self.errors
        }


@dataclass
class CrossChunkContext:
    """
    跨块上下文信息，用于在处理多个文档块时维持上下文连贯性。

    属性：
        previous_summary: 前一个块的摘要
        key_entities: 已知的关键实体列表（人名、术语等）
        pending_references: 前文提到但尚未解答的问题
        topic_continuation: 主题延续描述
        open_sections: 仍未关闭的章节/小节列表

    未使用说明：随 agents 模块整体保留，当前无调用方。
    """

    previous_summary: str = ""
    key_entities: List[str] = field(default_factory=list)
    pending_references: List[str] = field(default_factory=list)
    topic_continuation: str = ""
    open_sections: List[str] = field(default_factory=list)

    def merge(self, other: 'CrossChunkContext'):
        """
        将另一个跨块上下文合并到当前实例中。

        参数：
            other: 另一个 CrossChunkContext 实例
        """
        self.previous_summary = other.previous_summary
        self.key_entities = list(set(self.key_entities + other.key_entities))
        self.pending_references = list(set(self.pending_references + other.pending_references))
        if other.topic_continuation:
            self.topic_continuation = other.topic_continuation
        self.open_sections = list(set(self.open_sections + other.open_sections))

    def to_prompt_context(self) -> str:
        """
        将上下文转换为供 LLM 使用的提示文本。

        返回：
            格式化的上下文字符串，每项占一行
        """
        parts = []
        if self.previous_summary:
            parts.append(f"前文摘要：{self.previous_summary}")
        if self.key_entities:
            parts.append(f"已知实体：{', '.join(self.key_entities[:10])}")
        if self.pending_references:
            parts.append(f"待解答问题：{', '.join(self.pending_references[:5])}")
        if self.topic_continuation:
            parts.append(f"主题延续：{self.topic_continuation}")
        return "\n".join(parts) if parts else ""


class MessageBus:
    """
    基于发布-订阅模式的消息总线，用于多智能体之间的通信。

    使用方式：
        bus = MessageBus()
        bus.subscribe("topic_a", my_callback)
        bus.publish("topic_a", {"data": "hello"})

    未使用说明：随 agents 模块整体保留，当前无调用方。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: Dict[str, List[Callable]] = {}
        self._messages: List[Dict] = []

    def subscribe(self, topic: str, callback: Callable):
        """
        订阅某个主题的消息。

        参数：
            topic: 主题名称
            callback: 收到消息时的回调函数，签名为 callback(message: Dict)
        """
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(callback)

    def publish(self, topic: str, message: Dict):
        """
        向指定主题发布消息，触发所有该主题的订阅回调。

        参数：
            topic: 主题名称
            message: 消息内容字典
        """
        with self._lock:
            self._messages.append({"topic": topic, "data": message, "ts": threading.time()})
            if topic in self._subscribers:
                for cb in self._subscribers[topic]:
                    try:
                        cb(message)
                    except Exception as e:
                        logger.warning(f"MessageBus callback error: {e}")

    def get_messages(self, topic: Optional[str] = None, since: float = 0) -> List[Dict]:
        """
        获取历史消息。

        参数：
            topic: 如果指定，只返回该主题的消息；否则返回所有主题
            since: 只返回时间戳大于此值的消息（默认 0 表示全部）

        返回：
            消息字典列表
        """
        with self._lock:
            if topic:
                return [m for m in self._messages if m["topic"] == topic and m["ts"] > since]
            return [m for m in self._messages if m["ts"] > since]
