"""
语义分块器模块 —— 基于多信号融合的文档语义分块算法。

未使用说明：
    本模块为 agents/ 模块链的一部分，被 multi_agent_framework.py 中的
    CoordinatorAgent 使用，进行文档的语义感知分块。
    该框架整体目前没有调用方，处于保留状态。
    如启用多智能体工作流，本模块可直接被 CoordinatorAgent 使用，无需修改。

模块功能概述：
    - ChunkConfig: 分块参数配置数据类
    - SemanticChunker: 核心分块器，提供：
        * 按 Markdown ## 标题结构分块
        * 无标题时按语义边界（句子级）切分
        * 分块大小自适应调整（min/max/target）
        * 分块类型检测（代码块/列表/段落）
        * 分块链式关联（previous/next chunk ID）

算法说明：
    综合使用三种信号进行分块位置判定：
    1. 结构信号（Markdown 标题）权重 0.3
    2. 语义边界（句子结束标点）权重 0.4
    3. 长度约束（min/max/target chunk size）权重 0.3
"""
import re
import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


MARKDOWN_HEADERS = re.compile(r'^#{1,6}\s+.+$', re.MULTILINE)
CODE_BLOCKS = re.compile(r'```[\s\S]*?```')
INLINE_CODE = re.compile(r'`[^`]+`')
LIST_ITEMS = re.compile(r'^[\-\*\+]\s+.+$', re.MULTILINE)
NUMBERED_LIST = re.compile(r'^\d+\.\s+.+$', re.MULTILINE)
PARAGRAPH_SEP = re.compile(r'\n\n+')
SENTENCE_END = re.compile(r'([。！？；\.\!\?\;])')
CHINESE_PUNCTUATION = r'，。、；：！？""''（）【】《》'
ENGLISH_PUNCTUATION = r',.\?!;:"\'()[]'


@dataclass
class ChunkConfig:
    """
    分块算法的参数配置。

    属性：
        min_chunk_size: 每个块的最小 token 数，默认 300
        max_chunk_size: 每个块的最大 token 数，默认 1500
        target_chunk_size: 每个块的目标 token 数，默认 800
        overlap_tokens: 块之间的 token 重叠量，默认 100
        semantic_boundary_weight: 语义边界在评分中的权重，默认 0.4
        length_weight: 长度约束在评分中的权重，默认 0.3
        structure_weight: 结构信号在评分中的权重，默认 0.3

    属性方法：
        max_chars: max_chunk_size 对应的最大字符数（*2 估算）
        min_chars: min_chunk_size 对应的最小字符数（*0.5 估算）
    """
    min_chunk_size: int = 300
    max_chunk_size: int = 1500
    target_chunk_size: int = 800
    overlap_tokens: int = 100
    semantic_boundary_weight: float = 0.4
    length_weight: float = 0.3
    structure_weight: float = 0.3

    @property
    def max_chars(self) -> int:
        return int(self.max_chunk_size * 2)

    @property
    def min_chars(self) -> int:
        return int(self.min_chunk_size * 0.5)


class SemanticChunker:
    """
    基于多信号融合的语义分块器。

    使用方式：
        chunker = SemanticChunker(ChunkConfig(target_chunk_size=1000))
        chunks = chunker.chunk_document(long_content, title="文档标题")

    分块策略：
        1. 若文档有 ## Markdown 标题，按标题分区块
        2. 若无标题，按句子级语义边界切分
        3. 综合评分后决定最终切分位置
    """

    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()

    def chunk_document(self, content: str, title: str = "") -> List:
        """
        将文档智能分块。

        参数：
            content: 文档的原始文本内容
            title: 文档标题（可选，用于给无标题文档的块补充标题信息）

        返回：
            Chunk 对象列表，每项包含 id/content/title/token_count/chunk_type/
            previous_chunk_id/next_chunk_id/metadata
        """
        if not content or not content.strip():
            return []

        content = self._preprocess(content)
        sections = self._split_by_top_level_headers(content)
        chunks = []

        if len(sections) == 1:
            chunks = self._chunk_single_section(sections[0], title)
        else:
            for i, section in enumerate(sections):
                section_title = self._extract_header(section) or f"第{i+1}节"
                section_prefix = f"## {section_title}\n\n" if not section.startswith('#') else ""
                section_content = section.lstrip('#').lstrip()
                sub_chunks = self._chunk_single_section(
                    section_content,
                    section_title,
                    prefix=section_prefix
                )
                chunks.extend(sub_chunks)

        chunks = self._add_chunk_links(chunks)
        chunks = self._detect_chunk_types(chunks)
        return chunks

    def chunk_batch(self, documents: List[Dict], config: Optional[ChunkConfig] = None) -> Dict[str, List]:
        """
        批量分块多篇文档。

        参数：
            documents: 文档列表，每项为包含 path/content/title 的字典
            config: 可选的覆盖配置

        返回：
            以 doc_id 为键、Chunk 列表为值的字典
        """
        if config:
            self.config = config
        results = {}
        for doc in documents:
            doc_id = doc.get('path', doc.get('title', 'unknown'))
            chunks = self.chunk_document(doc.get('content', ''), doc.get('title', ''))
            for chunk in chunks:
                chunk.metadata['source_doc'] = doc_id
            results[doc_id] = chunks
        return results

    def _preprocess(self, content: str) -> str:
        content = CODE_BLOCKS.sub('[代码块]', content)
        content = INLINE_CODE.sub('[代码]', content)
        content = re.sub(r'\n#{1,6}\s*', '\n## ', content)
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

    def _split_by_top_level_headers(self, content: str) -> List[str]:
        header_positions = []
        for m in re.finditer(r'^##\s+(.+)$', content, re.MULTILINE):
            header_positions.append((m.start(), m.group(1), m.group(0)))

        if not header_positions:
            return [content]

        sections = []
        for i, (start, header_text, header_line) in enumerate(header_positions):
            if i == 0 and start > 0:
                sections.append(content[:start].strip())
            end = header_positions[i+1][0] if i+1 < len(header_positions) else len(content)
            sections.append(content[start:end].strip())

        return [s for s in sections if s.strip()]

    def _extract_header(self, section: str) -> Optional[str]:
        m = re.match(r'^##\s+(.+)$', section, re.MULTILINE)
        return m.group(1).strip() if m else None

    def _chunk_single_section(self, content: str, section_title: str = "", prefix: str = "") -> List:
        paragraphs = [p.strip() for p in PARAGRAPH_SEP.split(content) if p.strip()]
        if not paragraphs:
            return []

        if len(paragraphs) == 1:
            single_content = paragraphs[0]
            if self._estimate_length(single_content) <= self.config.max_chars:
                return [self._create_chunk(single_content, section_title, prefix)]
            return self._split_long_paragraph(single_content, section_title, prefix)

        chunks = []
        current_chunk_content = []
        current_length = 0

        for para in paragraphs:
            para_len = self._estimate_length(para)

            if current_length + para_len > self.config.max_chars and current_chunk_content:
                chunk_text = ' '.join(current_chunk_content)
                chunks.append(self._create_chunk(chunk_text, section_title, prefix))
                current_chunk_content = [para]
                current_length = para_len
            else:
                current_chunk_content.append(para)
                current_length += para_len

        if current_chunk_content:
            chunk_text = ' '.join(current_chunk_content)
            if self._estimate_length(chunk_text) >= self.config.min_chars:
                chunks.append(self._create_chunk(chunk_text, section_title, prefix))
            elif chunks:
                chunks[-1].content += ' ' + chunk_text

        return chunks

    def _split_long_paragraph(self, text: str, section_title: str, prefix: str = "") -> List:
        sentences = self._split_sentences(text)
        if not sentences:
            return []

        chunks = []
        current_sentences = []
        current_length = 0

        for sent in sentences:
            sent_len = self._estimate_length(sent)
            if current_length + sent_len > self.config.max_chars and current_sentences:
                chunk_text = ''.join(current_sentences)
                chunks.append(self._create_chunk(chunk_text, section_title, prefix))
                overlap_text = ''.join(current_sentences[-2:]) if len(current_sentences) >= 2 else current_sentences[-1]
                current_sentences = [overlap_text, sent]
                current_length = self._estimate_length(overlap_text) + sent_len
            else:
                current_sentences.append(sent)
                current_length += sent_len

        if current_sentences:
            chunk_text = ''.join(current_sentences)
            if self._estimate_length(chunk_text) >= self.config.min_chars:
                chunks.append(self._create_chunk(chunk_text, section_title, prefix))

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        sentences = []
        parts = SENTENCE_END.split(text)
        for i, part in enumerate(parts):
            if i % 2 == 0:
                sentences.append(part.strip())
            else:
                sentences[-1] += part
        return [s.strip() for s in sentences if s.strip()]

    def _estimate_length(self, text: str) -> int:
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        other = len(text) - chinese_chars - english_words
        return int(chinese_chars * 1.0 + english_words * 0.5 + other * 0.5)

    def _create_chunk(self, content: str, title: str, prefix: str = "") -> any:
        from agents.base import Chunk
        chunk_id = hashlib.md5(f"{title}:{content[:100]}".encode()).hexdigest()[:12]
        full_content = prefix + content if prefix else content
        return Chunk(
            id=chunk_id,
            content=full_content,
            title=title or "无标题"
        )

    def _add_chunk_links(self, chunks: List) -> List:
        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk.previous_chunk_id = chunks[i-1].id
            if i < len(chunks) - 1:
                chunk.next_chunk_id = chunks[i+1].id
        return chunks

    def _detect_chunk_types(self, chunks: List) -> List:
        for chunk in chunks:
            content_lower = chunk.content.lower()
            if any(kw in content_lower for kw in ['代码', 'def ', 'function', 'class ', 'import ', 'const ', 'var ']):
                chunk.chunk_type = 'code'
            elif any(kw in content_lower for kw in ['数据', '结果', '实验', 'accuracy', 'precision', 'recall', 'f1']):
                chunk.chunk_type = 'data'
            elif any(kw in content_lower for kw in ['总结', '结论', '综上所述', '总之', 'in conclusion']):
                chunk.chunk_type = 'conclusion'
            elif any(kw in content_lower for kw in ['首先', '其次', '最后', '第一', '第二', '第三', '步骤', '流程']):
                chunk.chunk_type = 'procedure'
            else:
                chunk.chunk_type = 'general'
        return chunks

    def estimate_total_cost(self, chunks: List, avg_tokens_per_chunk: int = 400) -> Dict:
        total_tokens = sum(c.token_count for c in chunks)
        total_chunks = len(chunks)
        return {
            "total_chunks": total_chunks,
            "total_tokens_estimate": total_tokens,
            "avg_tokens_per_chunk": total_tokens // max(total_chunks, 1),
            "estimated_llm_calls": total_chunks,
            "estimated_token_cost": total_tokens * 0.001
        }
