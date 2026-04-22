import re
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional, Callable

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import config
from utils.logger import logger
from utils.helpers import (
    sanitize_filename, clean_text, extract_title_from_markdown,
    check_api_config, APIConfigError, NetworkError, is_network_error
)
from utils.tag_extractor import process_and_tag_file
from prompts.note_integration import (
    CONTENT_INTEGRATION_PROMPT,
    TOPIC_INTEGRATION_PROMPT,
    TOPIC_EXTRACTION_PROMPT,
    CHUNK_COMPRESSION_PROMPT,
    TOPIC_NOTE_GENERATION_PROMPT
)

class NoteIntegration:
    """笔记整合器"""

    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback
        self.documents = []
    
    def load_documents_from_folder(self, folder_path: str) -> List[Dict]:
        """从文件夹加载Markdown文档"""
        folder = Path(folder_path)
        documents = []

        if not folder.exists():
            logger.error(f"文件夹不存在: {folder_path}")
            return documents

        md_files = list(folder.rglob("*.md"))
        max_total = 0.5

        for i, md_file in enumerate(md_files):
            if self.progress_callback:
                self.progress_callback(i + 1, len(md_files), f"读取 MD 文件中 - {md_file.name}", max_total)

            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                title = extract_title_from_markdown(content) or md_file.stem
                
                documents.append({
                    'path': str(md_file),
                    'title': title,
                    'content': content,
                    'filename': md_file.name
                })
                
            except Exception as e:
                logger.error(f"加载文件失败 {md_file}: {e}")
        
        self.documents = documents
        logger.info(f"已加载 {len(documents)} 个文档")
        return documents
    
    
    
    
    
    
    def integrate(
        self,
        documents: List[Dict],
        save_path: str = None,
        strategy: str = "topic_v2",
        user_topics: List[str] = None
    ) -> Dict:
        """统一的笔记整合入口

        Args:
            documents: 文档列表 [{title, content, path}, ...]
            save_path: 保存路径
            strategy: 整合策略（仅支持 topic_v2）
            user_topics: 用户指定的主题列表
        """
        return self._integrate_by_topics_v2(documents, save_path, user_topics)

    def _integrate_by_topics_v2(
        self,
        documents: List[Dict],
        save_path: str = None,
        user_topics: List[str] = None
    ) -> Dict:
        """基于 Heading 拆分的笔记整合策略

        流程：
        1. 提取文档标题 + 按 Heading 拆分 chunks
        2. LLM 提取主题 + 块归属映射
        3. 对每个主题：拼接内容 → 判断压缩 → LLM 生成
        4. 输出独立文件
        """
        is_valid, error_msg = check_api_config()
        if not is_valid:
            logger.error(f"API配置检查失败: {error_msg}")
            raise APIConfigError(error_msg)

        try:
            current_step = [0]

            def report_progress(step_msg, overall):
                if self.progress_callback:
                    self.progress_callback(1, 1, step_msg, overall)

            current_step[0] = 1
            report_progress("阶段1/4: 提取文档信息...", 0.1)

            docs_for_extraction = [{'title': d.get('title', ''), 'path': d.get('path', ''), 'filename': d.get('filename', '')} for d in documents]
            chunks = self._split_documents_by_heading(docs_for_extraction)

            report_progress(f"阶段1/4: 拆分完成，共 {len(chunks)} 个模块", 0.2)

            current_step[0] = 2
            report_progress("阶段2/4: 提取主题和块归属...", 0.3)

            if user_topics:
                topics = [{"name": t, "description": "", "chunk_ids": []} for t in user_topics]
                topic_chunk_mapping = self._map_chunks_to_user_topics(user_topics, chunks)
                for topic in topics:
                    topic_name = topic['name']
                    if topic_name in topic_chunk_mapping:
                        topic['chunk_ids'] = topic_chunk_mapping[topic_name]
                    logger.info(f"使用用户指定主题: {topic_name}, 关联 {len(topic['chunk_ids'])} 个 chunks")
            else:
                topic_result = self._extract_topics_with_mapping(docs_for_extraction, chunks)
                topics = topic_result['topics']
                topic_chunk_mapping = topic_result['topic_chunk_mapping']

                for topic in topics:
                    topic_name = topic['name']
                    if topic_name in topic_chunk_mapping:
                        topic['chunk_ids'] = topic_chunk_mapping[topic_name]
                    else:
                        topic['chunk_ids'] = []

            report_progress(f"阶段2/4: 提取了 {len(topics)} 个主题", 0.4)

            current_step[0] = 3
            topic_results = []

            def process_one(topic):
                return self._process_topic(topic, chunks)

            with ThreadPoolExecutor(max_workers=min(len(topics), 4)) as executor:
                future_to_topic = {executor.submit(process_one, t): t for t in topics}
                for future in as_completed(future_to_topic):
                    topic_name = future_to_topic[future]["name"]
                    report_progress(f"阶段3/4: 处理主题「{topic_name}」", -1)
                    try:
                        topic_results.append(future.result())
                    except Exception as e:
                        logger.error(f"处理主题失败 {topic_name}: {e}")

            report_progress("阶段3/4: 主题处理完成", 0.8)

            current_step[0] = 4
            report_progress("阶段4/4: 生成文件...", 0.9)

            output_files = []
            save_dir = Path(save_path) if save_path else Path(config.get_output_folder())

            for result in topic_results:
                safe_name = sanitize_filename(result['topic_name'])
                output_file = save_dir / f"{safe_name}.md"
                output_file.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(result['content'])

                process_and_tag_file(str(output_file))
                output_files.append(str(output_file))

            report_progress(f"阶段4/4: 生成完成，共 {len(output_files)} 个文件", 1.0)

            return {
                'content': '\n\n---\n\n'.join([r['content'] for r in topic_results]),
                'document_count': len(documents),
                'chunk_count': len(chunks),
                'topic_count': len(topics),
                'topics': [t['name'] for t in topics],
                'file_paths': output_files
            }

        except APIConfigError:
            raise
        except Exception as e:
            if is_network_error(e):
                logger.error(f"大模型服务网络连接失败: {e}")
                raise NetworkError("大模型服务连接失败，请检查您的网络连接状态后重试")
            logger.error(f"V2整合失败: {e}")
            raise

    def _process_topic(self, topic_info: Dict, chunks: List[Dict]) -> Dict:
        """处理单个主题的内容"""
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate

        topic_name = topic_info['name']
        chunk_ids = topic_info.get('chunk_ids', [])

        topic_chunks = [c for c in chunks if c['chunk_id'] in chunk_ids]
        topic_chunks.sort(key=lambda x: x['source_order'])

        original_word_count = sum(c['word_count'] for c in topic_chunks)
        threshold = config.max_tokens * 0.9 * 4
        was_compressed = False

        if original_word_count > threshold:
            compression_ratio = threshold / original_word_count
            logger.info(f"主题「{topic_name}」需要压缩，比例: {compression_ratio:.2f}")

            compressed_chunks = []
            for chunk in topic_chunks:
                compressed = self._compress_chunk(chunk, compression_ratio)
                compressed_chunks.append(compressed)
                was_compressed = True

            final_content = '\n\n'.join([c['content'] for c in compressed_chunks])
            final_word_count = sum(c['word_count'] for c in compressed_chunks)
        else:
            final_content = '\n\n'.join([c['content'] for c in topic_chunks])
            final_word_count = original_word_count

        generated_content = self._generate_topic_note(
            topic_name,
            final_content,
            final_word_count
        )

        return {
            'topic_name': topic_name,
            'content': generated_content,
            'source_chunks': chunk_ids,
            'was_compressed': was_compressed,
            'original_word_count': original_word_count
        }

    def _map_chunks_to_user_topics(self, user_topics: List[str], chunks: List[Dict]) -> Dict[str, List[str]]:
        """使用 LLM 将 chunks 映射到用户指定的主题

        Args:
            user_topics: 用户指定的主题列表
            chunks: 文档拆分后的块列表

        Returns:
            {主题名称: [chunk_id, ...], ...}
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate

        topic_chunk_mapping = {t: [] for t in user_topics}

        chunks_info = '\n'.join([
            f"- {c['chunk_id']}: {c['content'][:150]}... ({c['word_count']}字)"
            for c in chunks[:80]
        ])
        if len(chunks) > 80:
            chunks_info += f"\n- ... 还有 {len(chunks) - 80} 个 chunks"

        topics_text = '\n'.join([f"{i+1}. {t}" for i, t in enumerate(user_topics)])

        mapping_prompt = """你是一位专业的知识整理专家。以下是多个内容块和一组主题：

主题列表：
{topics}

内容块：
{chunks_info}

请将每个内容块分配到最相关的主题中。一个内容块可以属于多个主题。

请以以下JSON格式输出：
{{
    "mapping": {{
        "主题名称": ["chunk_id_1", "chunk_id_2", ...],
        ...
    }}
}}

注意：
- 每个chunk至少归属一个主题
- 如果某个主题没有相关chunk，其列表为空
- 确保所有chunk_id都存在于输入中"""

        prompt = PromptTemplate(
            template=mapping_prompt,
            input_variables=["topics", "chunks_info"]
        )
        llm = ChatOpenAI(
            api_key=config.api_key,
            base_url=config.api_base,
            model=config.model_name,
            temperature=0.3,
            max_tokens=config.max_tokens
        )
        chain = prompt | llm

        try:
            if self.progress_callback:
                self.progress_callback(1, 1, "大模型思考中 - 映射内容块到主题", -1)
            response = chain.invoke({
                "topics": topics_text,
                "chunks_info": chunks_info
            })
            result = json.loads(response.content)
            mapping = result.get('mapping', {})

            for topic_name, chunk_ids in mapping.items():
                if topic_name in topic_chunk_mapping:
                    topic_chunk_mapping[topic_name] = chunk_ids

            logger.info(f"用户主题映射完成: {[(t, len(ids)) for t, ids in topic_chunk_mapping.items()]}")
            return topic_chunk_mapping

        except Exception as e:
            logger.warning(f"LLM 主题映射失败，使用关键词匹配: {e}")
            return self._fallback_chunk_mapping(user_topics, chunks)

    def _fallback_chunk_mapping(self, user_topics: List[str], chunks: List[Dict]) -> Dict[str, List[str]]:
        """降级策略：基于关键词匹配将 chunks 分配到主题"""
        topic_chunk_mapping = {t: [] for t in user_topics}

        for chunk in chunks:
            content_lower = chunk['content'].lower()
            for topic in user_topics:
                if topic.lower() in content_lower:
                    topic_chunk_mapping[topic].append(chunk['chunk_id'])

        for topic in user_topics:
            if not topic_chunk_mapping[topic]:
                topic_chunk_mapping[topic] = [c['chunk_id'] for c in chunks[:max(1, len(chunks) // len(user_topics))]]

        return topic_chunk_mapping

    def _split_documents_by_heading(self, documents: List[Dict]) -> List[Dict]:
        """按 Heading 拆分文档为 chunks

        Args:
            documents: [{title, path, filename}, ...]

        Returns:
            chunks: [{chunk_id, doc_id, content, word_count, source_order}, ...]
        """
        chunks = []
        chunk_counter = 0

        for doc_id, doc in enumerate(documents):
            try:
                with open(doc['path'], 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"读取文件失败 {doc['path']}: {e}")
                continue

            heading_pattern = re.compile(r'^#{1,3}\s+.+$', re.MULTILINE)
            matches = list(heading_pattern.finditer(content))

            if not matches:
                word_count = self._count_words(content)
                if word_count > 0:
                    chunks.append({
                        'chunk_id': f'chunk_{chunk_counter}',
                        'doc_id': doc_id,
                        'content': content.strip(),
                        'word_count': word_count,
                        'source_order': chunk_counter
                    })
                    chunk_counter += 1
                continue

            for i, match in enumerate(matches):
                heading_start = match.start()
                heading_end = match.end()
                heading_text = match.group()

                if i + 1 < len(matches):
                    next_heading_start = matches[i + 1].start()
                    chunk_content = content[heading_start:next_heading_start].strip()
                else:
                    chunk_content = content[heading_start:].strip()

                word_count = self._count_words(chunk_content)

                if word_count < 100 and chunks:
                    chunks[-1]['content'] += '\n\n' + chunk_content
                    chunks[-1]['word_count'] += word_count
                elif word_count >= 100:
                    if word_count > 500:
                        sub_chunks = self._split_large_chunk(chunk_content, chunk_counter)
                        for sub_chunk in sub_chunks:
                            sub_chunk['doc_id'] = doc_id
                            sub_chunk['source_order'] = chunk_counter
                            chunks.append(sub_chunk)
                            chunk_counter += 1
                    else:
                        chunks.append({
                            'chunk_id': f'chunk_{chunk_counter}',
                            'doc_id': doc_id,
                            'content': chunk_content,
                            'word_count': word_count,
                            'source_order': chunk_counter
                        })
                        chunk_counter += 1

        logger.info(f"按Heading拆分为 {len(chunks)} 个 chunks")
        return chunks

    def _split_large_chunk(self, content: str, start_counter: int) -> List[Dict]:
        """将大块内容拆分为 100-500 字的小块"""
        chunks = []
        paragraphs = re.split(r'\n\n+', content)
        current_chunk = ''
        current_count = 0
        counter = start_counter

        for para in paragraphs:
            para_count = self._count_words(para)

            if current_count + para_count <= 500:
                current_chunk += '\n\n' + para if current_chunk else para
                current_count += para_count
            else:
                if current_chunk:
                    chunks.append({
                        'chunk_id': f'chunk_{counter}',
                        'doc_id': 0,
                        'content': current_chunk.strip(),
                        'word_count': current_count,
                        'source_order': counter
                    })
                    counter += 1

                if para_count > 500:
                    sentences = re.split(r'([。！？.!?])', para)
                    temp_sentence = ''
                    temp_count = 0

                    for j, part in enumerate(sentences):
                        part_count = self._count_words(part)
                        if j % 2 == 0:
                            if temp_count + part_count <= 500:
                                temp_sentence += part
                                temp_count += part_count
                            else:
                                if temp_sentence:
                                    chunks.append({
                                        'chunk_id': f'chunk_{counter}',
                                        'doc_id': 0,
                                        'content': temp_sentence.strip(),
                                        'word_count': temp_count,
                                        'source_order': counter
                                    })
                                    counter += 1
                                temp_sentence = part
                                temp_count = part_count
                        else:
                            temp_sentence += part
                            temp_count += part_count

                    if temp_sentence and temp_count >= 100:
                        chunks.append({
                            'chunk_id': f'chunk_{counter}',
                            'doc_id': 0,
                            'content': temp_sentence.strip(),
                            'word_count': temp_count,
                            'source_order': counter
                        })
                        counter += 1
                else:
                    current_chunk = para
                    current_count = para_count

        if current_chunk and current_count >= 100:
            chunks.append({
                'chunk_id': f'chunk_{counter}',
                'doc_id': 0,
                'content': current_chunk.strip(),
                'word_count': current_count,
                'source_order': counter
            })

        return chunks

    def _count_words(self, text: str) -> int:
        """统计中文字符数（包含英文单词）"""
        if not text:
            return 0
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        return chinese_chars + english_words

    def _extract_topics_with_mapping(self, documents: List[Dict], chunks: List[Dict]) -> Dict:
        """LLM 提取主题和块归属映射

        Returns:
            {
                "topics": [{"name": str, "description": str}, ...],
                "topic_chunk_mapping": {"topic_name": ["chunk_id", ...], ...}
            }
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate

        total_words = sum(c['word_count'] for c in chunks)
        max_input = config.max_tokens * 4
        min_topic_count = math.ceil(total_words / max_input) if max_input > 0 else 1

        titles = '\n'.join([f"{i+1}. {doc.get('title', '未命名')}" for i, doc in enumerate(documents)])

        chunks_info = '\n'.join([
            f"- {c['chunk_id']}: {c['content'][:100]}... ({c['word_count']}字)"
            for c in chunks[:50]
        ])
        if len(chunks) > 50:
            chunks_info += f"\n- ... 还有 {len(chunks) - 50} 个 chunks"

        prompt = PromptTemplate(
            template=TOPIC_EXTRACTION_PROMPT,
            input_variables=["titles", "chunks_info", "total_words", "max_input", "min_topic_count"]
        )
        llm = ChatOpenAI(
            api_key=config.api_key,
            base_url=config.api_base,
            model=config.model_name,
            temperature=0.5,
            max_tokens=config.max_tokens
        )
        chain = prompt | llm

        try:
            if self.progress_callback:
                self.progress_callback(1, 1, "大模型思考中 - 提取主题和块归属映射", -1)
            response = chain.invoke({
                "titles": titles,
                "chunks_info": chunks_info,
                "total_words": total_words,
                "max_input": max_input,
                "min_topic_count": min_topic_count
            })

            result = json.loads(response.content)

            topics = result.get('topics', [])
            topic_chunk_mapping = result.get('topic_chunk_mapping', {})

            if not topics or not topic_chunk_mapping:
                logger.warning("LLM 返回格式异常，使用降级策略")
                return self._fallback_topic_extraction(chunks, min_topic_count)

            for topic_info in topics:
                if 'description' not in topic_info:
                    topic_info['description'] = ''

            logger.info(f"提取了 {len(topics)} 个主题")
            return {
                "topics": topics,
                "topic_chunk_mapping": topic_chunk_mapping
            }

        except json.JSONDecodeError as e:
            logger.warning(f"解析JSON失败: {e}，使用降级策略")
            return self._fallback_topic_extraction(chunks, min_topic_count)
        except Exception as e:
            logger.error(f"主题提取失败: {e}")
            return self._fallback_topic_extraction(chunks, min_topic_count)

    def _fallback_topic_extraction(self, chunks: List[Dict], min_topic_count: int) -> Dict:
        """降级策略：基于 Heading 关键词提取主题"""
        heading_keywords = {}
        for chunk in chunks:
            heading_match = re.match(r'^#{1,3}\s+(.+?)(?:\n|$)', chunk['content'])
            if heading_match:
                keyword = heading_match.group(1).strip()[:20]
                if keyword not in heading_keywords:
                    heading_keywords[keyword] = []
                heading_keywords[keyword].append(chunk['chunk_id'])

        topics = []
        topic_chunk_mapping = {}

        for i, (keyword, chunk_ids) in enumerate(list(heading_keywords.items())[:max(min_topic_count, 5)]):
            topic_name = keyword if keyword else f"主题{i+1}"
            topics.append({"name": topic_name, "description": ""})
            topic_chunk_mapping[topic_name] = chunk_ids

        return {
            "topics": topics,
            "topic_chunk_mapping": topic_chunk_mapping
        }

    def _compress_chunk(self, chunk: Dict, compression_ratio: float) -> Dict:
        """LLM 按比例压缩单个 chunk

        Args:
            chunk: {chunk_id, content, word_count, ...}
            compression_ratio: 压缩比例 (0 < ratio < 1)

        Returns:
            压缩后的 chunk（包含原文字数和压缩后字数）
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate

        prompt = PromptTemplate(
            template=CHUNK_COMPRESSION_PROMPT,
            input_variables=["original_content", "target_ratio"]
        )
        llm = ChatOpenAI(
            api_key=config.api_key,
            base_url=config.api_base,
            model=config.model_name,
            temperature=0.3,
            max_tokens=config.max_tokens
        )
        chain = prompt | llm

        try:
            if self.progress_callback:
                self.progress_callback(1, 1, "大模型思考中 - 压缩内容块", -1)
            response = chain.invoke({
                "original_content": chunk['content'],
                "target_ratio": compression_ratio
            })

            compressed_content = clean_text(response.content)
            compressed_word_count = self._count_words(compressed_content)

            return {
                **chunk,
                'content': compressed_content,
                'word_count': compressed_word_count,
                'original_word_count': chunk['word_count']
            }
        except Exception as e:
            logger.warning(f"压缩chunk失败 {chunk['chunk_id']}: {e}，使用原始内容")
            return chunk

    def _generate_topic_note(self, topic_name: str, content: str, target_word_count: int) -> str:
        """LLM 生成主题笔记

        Args:
            topic_name: 主题名称
            content: 合并后的内容
            target_word_count: 目标字数（用于指示LLM保持相近篇幅）

        Returns:
            生成的主题笔记内容
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate

        prompt = PromptTemplate(
            template=TOPIC_NOTE_GENERATION_PROMPT,
            input_variables=["topic_name", "content", "target_word_count"]
        )
        llm = ChatOpenAI(
            api_key=config.api_key,
            base_url=config.api_base,
            model=config.model_name,
            temperature=0.4,
            max_tokens=config.max_tokens
        )
        chain = prompt | llm

        try:
            if self.progress_callback:
                self.progress_callback(1, 1, f"大模型思考中 - 生成主题「{topic_name}」笔记", -1)
            response = chain.invoke({
                "topic_name": topic_name,
                "content": content,
                "target_word_count": target_word_count
            })
            return clean_text(response.content)
        except Exception as e:
            logger.error(f"生成主题笔记失败 {topic_name}: {e}")
            return f"# {topic_name}\n\n内容生成失败，请参考源文档。"

