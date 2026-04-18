"""
上下文管理器模块 —— 为多智能体框架提供跨块上下文维护能力。

未使用说明：
    本模块为 agents/ 模块链的一部分，与 agents/base.py、
    agents/semantic_chunker.py、agents/multi_agent_framework.py 共同构成
    一套多智能体协作式文档处理框架。
    该框架目前没有任何调用方，处于保留状态。
    如未来需要实现"带实体追踪和上下文连贯性的笔记整合"，可直接启用此模块。

模块功能概述：
    - Entity: 命名实体（人名/机构/地点等）的数据结构
    - ContextManager: 线程安全的上下文管理器，维护：
        * 文档块摘要历史（最近 N 块的摘要）
        * 命名实体库（跨块实体追踪）
        * 跨块引用关系
        * 待解答问题队列
        * 当前主题栈
"""

import threading
from typing import Dict, List, Optional, Set
from collections import defaultdict
from dataclasses import dataclass, field


ENTITY_TYPES = [
    'person', 'organization', 'location', 'concept', 'event', 'object'
]


@dataclass
class Entity:
    """
    命名实体的数据结构。

    属性：
        name: 实体名称
        type: 实体类型（person/organization/location/concept/event/object）
        mentions: 该实体在哪些 chunk_id 中被提及
        first_seen_chunk: 首次出现所在的 chunk_id
        last_seen_chunk: 最近一次出现所在的 chunk_id
        description: 实体的描述信息
    """
    name: str
    type: str
    mentions: List[str] = field(default_factory=list)
    first_seen_chunk: str = ""
    last_seen_chunk: str = ""
    description: str = ""


class ContextManager:
    """
    线程安全的上下文管理器，用于在多智能体处理多个文档块时维持上下文连贯性。

    核心功能：
        1. 块摘要历史：维护最近 N 个块的摘要，供后续块参考
        2. 实体追踪：跨块识别和追踪命名实体（人名、机构、地点等）
        3. 引用关系：记录块与块之间的引用和待解答问题
        4. 主题管理：维护当前处理的主题栈

    线程安全：
        所有公共方法内部使用 threading.Lock 对共享状态进行保护，
        可安全地在多线程环境（如 ThreadPoolExecutor）中使用。

    使用示例：
        ctx = ContextManager(max_history=5)
        ctx.add_chunk_processed("chunk_1", "摘要文本", [{"name": "张三", "type": "person"}])
        prompt_context = ctx.build_context_prompt("chunk_2")
    """

    def __init__(self, max_history: int = 5):
        """
        初始化上下文管理器。

        参数：
            max_history: 保留的块摘要历史数量，默认 5
        """
        self.max_history = max_history
        self._lock = threading.Lock()
        self._entities: Dict[str, Entity] = {}
        self._chunk_summaries: Dict[str, str] = {}
        self._chunk_history: List[str] = []
        self._topic_stack: List[str] = []
        self._pending_references: Dict[str, List[str]] = defaultdict(list)
        self._cross_references: Dict[str, str] = {}

    def add_chunk_processed(self, chunk_id: str, summary: str, entities: List[Dict]):
        """
        记录一个块已处理完成，同时提取其中的实体。

        参数：
            chunk_id: 块的唯一标识
            summary: 该块的摘要文本
            entities: 该块中识别出的实体列表，每项为包含 name/type/description 的字典
        """
        with self._lock:
            self._chunk_summaries[chunk_id] = summary
            self._chunk_history.append(chunk_id)
            if len(self._chunk_history) > self.max_history:
                self._chunk_history.pop(0)

            for ent in entities:
                name = ent.get('name', '')
                if not name:
                    continue
                if name not in self._entities:
                    self._entities[name] = Entity(
                        name=name,
                        type=ent.get('type', 'concept'),
                        first_seen_chunk=chunk_id
                    )
                self._entities[name].mentions.append(chunk_id)
                self._entities[name].last_seen_chunk = chunk_id
                if ent.get('description'):
                    self._entities[name].description = ent['description']

    def get_recent_summaries(self, n: int = 3) -> str:
        """
        获取最近 N 个块的摘要。

        参数：
            n: 返回最近几条摘要，默认 3

        返回：
            各摘要用换行拼接的字符串
        """
        with self._lock:
            recent_ids = self._chunk_history[-n:]
            summaries = []
            for cid in recent_ids:
                if cid in self._chunk_summaries:
                    summaries.append(self._chunk_summaries[cid])
            return "\n".join(summaries)

    def get_entity_context(self, entity_name: str = None) -> str:
        """
        获取实体相关的上下文。

        参数：
            entity_name: 如果指定，返回该实体的详细信息；否则返回最近 10 个实体的摘要

        返回：
            格式化后的实体上下文字符串
        """
        with self._lock:
            if entity_name:
                if entity_name in self._entities:
                    e = self._entities[entity_name]
                    return f"{e.name}({e.type}): {e.description}"
                return ""
            parts = []
            for e in list(self._entities.values())[-10:]:
                parts.append(f"{e.name}({e.type})")
            return ", ".join(parts) if parts else "暂无"

    def add_cross_reference(self, from_chunk: str, to_chunk: str, reference_text: str = ""):
        """
        记录两个块之间的引用关系。

        参数：
            from_chunk: 引用来源块 ID
            to_chunk: 被引用的目标块 ID
            reference_text: 引用文本（如前文提到的问题）
        """
        with self._lock:
            self._cross_references[from_chunk] = to_chunk
            if reference_text:
                self._pending_references[to_chunk].append(reference_text)

    def get_pending_references(self, chunk_id: str) -> List[str]:
        """
        获取指向指定块的待解答问题列表。

        参数：
            chunk_id: 目标块的 ID

        返回：
            待解答问题的字符串列表
        """
        with self._lock:
            refs = self._pending_references.get(chunk_id, [])
            return list(refs)

    def push_topic(self, topic: str):
        """
        将新主题压入主题栈。

        参数：
            topic: 主题名称
        """
        with self._lock:
            self._topic_stack.append(topic)
            if len(self._topic_stack) > 10:
                self._topic_stack.pop(0)

    def get_current_topic(self) -> str:
        """
        获取当前主题（栈顶）。

        返回：
            当前主题字符串，空字符串表示无主题
        """
        with self._lock:
            return self._topic_stack[-1] if self._topic_stack else ""

    def build_context_prompt(self, chunk_id: str, include_entities: bool = True) -> str:
        """
        为指定块构建上下文字符串，可直接作为 LLM 提示词的一部分。

        格式：
            === 前文摘要 ===
            <摘要1>
            <摘要2>

            === 已识别实体 ===
            <实体列表>

            === 待解答问题 ===
            - <问题1>
            - <问题2>

            === 当前主题 ===
            <主题名>

        参数：
            chunk_id: 目标块的 ID（用于查找待解答问题）
            include_entities: 是否包含实体上下文，默认 True

        返回：
            格式化的上下文字符串
        """
        parts = []
        recent = self.get_recent_summaries(2)
        if recent:
            parts.append(f"=== 前文摘要 ===\n{recent}")
        if include_entities:
            entities = self.get_entity_context()
            if entities:
                parts.append(f"=== 已识别实体 ===\n{entities}")
        pending = self.get_pending_references(chunk_id)
        if pending:
            parts.append(f"=== 待解答问题 ===\n" + "\n".join(f"- {p}" for p in pending))
        current_topic = self.get_current_topic()
        if current_topic:
            parts.append(f"=== 当前主题 ===\n{current_topic}")
        return "\n\n".join(parts)

    def get_statistics(self) -> Dict:
        """
        获取当前上下文的统计信息。

        返回：
            包含 entity 数量、已处理块数、待解答引用数、当前主题的字典
        """
        with self._lock:
            return {
                "total_entities": len(self._entities),
                "total_chunks_processed": len(self._chunk_summaries),
                "pending_references": sum(len(v) for v in self._pending_references.values()),
                "current_topic": self.get_current_topic()
            }
