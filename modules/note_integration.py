import re
import json
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
from prompts.note_integration import TOPIC_NOTE_GENERATION_PROMPT

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
        user_topics: List[str] = None
    ) -> Dict:
        """笔记整合入口

        Args:
            documents: 文档列表 [{title, content, path}, ...]
            save_path: 保存路径
            user_topics: 已提取的主题列表
        """
        return self._integrate_by_topics(documents, save_path, user_topics)

    def _integrate_by_topics(
        self,
        documents: List[Dict],
        save_path: str = None,
        user_topics: List[str] = None
    ) -> Dict:
        """基于主题的笔记整合策略

        流程：
        1. 使用已提取的主题，将整个文件分配到最匹配的主题
        2. 对每个主题：拼接文件内容 → LLM 生成整合笔记
        3. 输出独立文件
        """
        is_valid, error_msg = check_api_config()
        if not is_valid:
            logger.error(f"API配置检查失败: {error_msg}")
            raise APIConfigError(error_msg)

        if not user_topics:
            raise APIConfigError("未提供主题列表，请先提取主题")

        try:
            def report_progress(step_msg, overall):
                if self.progress_callback:
                    self.progress_callback(1, 1, step_msg, overall)

            report_progress("阶段1/3: 分配文件到主题...", 0.1)

            topic_doc_mapping = self._map_documents_to_topics(user_topics, documents)

            for topic_name, doc_indices in topic_doc_mapping.items():
                logger.info(f"主题「{topic_name}」: {len(doc_indices)} 个文件")

            report_progress(f"阶段1/3: 分配完成", 0.3)

            report_progress("阶段2/3: 生成主题笔记...", 0.4)
            topic_results = []

            def process_one(topic_name, doc_indices):
                return self._process_topic(topic_name, documents, doc_indices)

            import multiprocessing
            max_workers = min(len(user_topics), multiprocessing.cpu_count() * 2)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_topic = {
                    executor.submit(process_one, name, indices): name
                    for name, indices in topic_doc_mapping.items()
                }
                for future in as_completed(future_to_topic):
                    topic_name = future_to_topic[future]
                    report_progress(f"阶段2/3: 处理主题「{topic_name}」", -1)
                    try:
                        topic_results.append(future.result())
                    except Exception as e:
                        logger.error(f"处理主题失败 {topic_name}: {e}")

            report_progress("阶段2/3: 主题处理完成", 0.8)

            report_progress("阶段3/3: 保存文件...", 0.9)

            output_files = []
            save_dir = Path(save_path) if save_path else Path(config.get_organized_folder())

            for result in topic_results:
                safe_name = sanitize_filename(result['topic_name'])
                output_file = save_dir / f"{safe_name}.md"
                output_file.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(result['content'])

                process_and_tag_file(str(output_file))
                output_files.append(str(output_file))

            report_progress("阶段3/3: 生成 WIKI.md 索引...", 0.95)

            wiki_content = self._generate_wiki_md(topic_results, output_files, save_dir)
            
            workspace_root = None
            if save_path:
                workspace_root = Path(save_path).parent
            elif config.workspace_path:
                workspace_root = Path(config.workspace_path)
            
            wiki_path = None
            if workspace_root and workspace_root.exists():
                wiki_path = workspace_root / "WIKI.md"
            else:
                wiki_path = save_dir / "WIKI.md"
            
            with open(wiki_path, 'w', encoding='utf-8') as f:
                f.write(wiki_content)
            
            logger.info(f"WIKI.md 已生成: {wiki_path}")

            report_progress(f"阶段3/3: 完成，共 {len(output_files)} 个文件", 1.0)

            return {
                'content': '\n\n---\n\n'.join([r['content'] for r in topic_results]),
                'document_count': len(documents),
                'topic_count': len(topic_results),
                'topics': [r['topic_name'] for r in topic_results],
                'file_paths': output_files,
                'wiki_path': str(wiki_path)
            }

        except APIConfigError:
            raise
        except Exception as e:
            if is_network_error(e):
                logger.error(f"大模型服务网络连接失败: {e}")
                raise NetworkError("大模型服务连接失败，请检查您的网络连接状态后重试")
            logger.error(f"整合失败: {e}")
            raise

    def _map_documents_to_topics(self, topics: List[str], documents: List[Dict]) -> Dict[str, List[int]]:
        """使用 LLM 将整个文件分配到最匹配的主题

        Args:
            topics: 主题列表
            documents: 文档列表

        Returns:
            {主题名称: [文档索引, ...], ...}
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate

        topic_doc_mapping = {t: [] for t in topics}

        docs_info = '\n'.join([
            f"- 文档{i}: {d.get('title', d.get('filename', '未命名'))}"
            for i, d in enumerate(documents)
        ])

        topics_text = '\n'.join([f"{i+1}. {t}" for i, t in enumerate(topics)])

        mapping_prompt = """你是一位专业的知识整理专家。以下是多个文档的标题和一组主题：

主题列表：
{topics}

文档列表：
{docs_info}

请将每个文档分配到最相关的主题中。一个文档只能归属一个最匹配的主题。

请以以下JSON格式输出：
{{
    "mapping": {{
        "主题名称": [文档索引, ...],
        ...
    }}
}}

注意：
- 每个文档必须且只能归属一个主题
- 选择与文档标题语义最匹配的主题
- 如果某个主题没有匹配的文档，其列表为空
- 文档索引从0开始"""

        prompt = PromptTemplate(
            template=mapping_prompt,
            input_variables=["topics", "docs_info"]
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
                self.progress_callback(1, 1, "大模型思考中 - 分配文件到主题", -1)
            response = chain.invoke({
                "topics": topics_text,
                "docs_info": docs_info
            })
            result = json.loads(response.content)
            mapping = result.get('mapping', {})

            for topic_name, doc_indices in mapping.items():
                if topic_name in topic_doc_mapping:
                    topic_doc_mapping[topic_name] = doc_indices
                else:
                    matched = next((t for t in topic_doc_mapping if t.strip() == topic_name.strip()), None)
                    if matched:
                        topic_doc_mapping[matched] = doc_indices

            logger.info(f"文件-主题映射完成: {[(t, len(ids)) for t, ids in topic_doc_mapping.items()]}")
            return topic_doc_mapping

        except Exception as e:
            logger.warning(f"LLM 文件-主题映射失败，使用关键词匹配: {e}")
            return self._fallback_doc_mapping(topics, documents)

    def _fallback_doc_mapping(self, topics: List[str], documents: List[Dict]) -> Dict[str, List[int]]:
        """降级策略：基于关键词匹配将文档分配到主题"""
        topic_doc_mapping = {t: [] for t in topics}

        for i, doc in enumerate(documents):
            title = doc.get('title', '').lower()
            content_lower = doc.get('content', '').lower()
            best_topic = None
            best_score = 0

            for topic in topics:
                topic_lower = topic.lower()
                score = 0
                if topic_lower in title:
                    score += 3
                if topic_lower in content_lower:
                    score += 1
                for word in topic_lower.split():
                    if word in title:
                        score += 2
                    if word in content_lower:
                        score += 1
                if score > best_score:
                    best_score = score
                    best_topic = topic

            if best_topic:
                topic_doc_mapping[best_topic].append(i)

        for topic in topics:
            if not topic_doc_mapping[topic]:
                remaining = [i for i in range(len(documents)) if i not in sum(topic_doc_mapping.values(), [])]
                if remaining:
                    topic_doc_mapping[topic] = [remaining[0]]

        return topic_doc_mapping

    def _process_topic(self, topic_name: str, documents: List[Dict], doc_indices: List[int]) -> Dict:
        """处理单个主题的内容

        Args:
            topic_name: 主题名称
            documents: 全部文档列表
            doc_indices: 属于该主题的文档索引列表

        Returns:
            {topic_name, content, document_count, original_word_count, source_files}
        """
        topic_docs = [documents[i] for i in doc_indices]

        combined_content = '\n\n---\n\n'.join([d['content'] for d in topic_docs])
        original_word_count = self._count_words(combined_content)

        generated_content = self._generate_topic_note(
            topic_name,
            combined_content,
            original_word_count
        )

        source_files = [
            {
                'path': d['path'],
                'filename': d['filename'],
                'title': d['title']
            }
            for d in topic_docs
        ]

        return {
            'topic_name': topic_name,
            'content': generated_content,
            'document_count': len(topic_docs),
            'original_word_count': original_word_count,
            'source_files': source_files
        }

    def _extract_heading_outline(self, content: str) -> List[Dict]:
        """从 Markdown 内容中提取标题大纲

        Args:
            content: Markdown 内容

        Returns:
            [{level: int, text: str}, ...]
        """
        import re
        pattern = r'^(#{1,6})\s+(.+)$'
        matches = re.finditer(pattern, content, re.MULTILINE)
        outline = []
        for match in matches:
            level = len(match.group(1))
            text = match.group(2).strip()
            outline.append({'level': level, 'text': text})
        return outline

    def _generate_wiki_md(self, topic_results: List[Dict], output_files: List[str], save_dir: Path) -> str:
        """生成 WIKI.md 内容

        Args:
            topic_results: 主题处理结果列表
            output_files: 输出文件路径列表（顺序与 topic_results 对应）
            save_dir: 输出目录

        Returns:
            WIKI.md 的完整内容
        """
        from datetime import datetime

        lines = []
        lines.append("# 笔记整合索引 (WIKI)")
        lines.append("")
        lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> 共处理 **{len(topic_results)}** 个主题")
        lines.append("")
        lines.append("---")
        lines.append("")

        lines.append("## 主题目录")
        lines.append("")
        for i, result in enumerate(topic_results):
            topic_name = result['topic_name']
            safe_name = sanitize_filename(topic_name)
            lines.append(f"{i+1}. [{topic_name}]({safe_name}.md) - {result['document_count']} 个源文件")
        lines.append("")
        lines.append("---")
        lines.append("")

        for i, result in enumerate(topic_results):
            topic_name = result['topic_name']
            safe_name = sanitize_filename(topic_name)
            source_files = result.get('source_files', [])
            output_file = Path(output_files[i]) if i < len(output_files) else None

            lines.append(f"## {topic_name}")
            lines.append("")

            lines.append("### 文件大纲")
            lines.append("")
            outline = self._extract_heading_outline(result['content'])
            if outline:
                for item in outline:
                    indent = "  " * (item['level'] - 1)
                    lines.append(f"{indent}- {item['text']}")
            else:
                lines.append("> 未检测到标题结构")
            lines.append("")

            lines.append("### 来源文件")
            lines.append("")
            if source_files:
                for j, sf in enumerate(source_files):
                    rel_path = None
                    try:
                        abs_path = Path(sf['path'])
                        if output_file:
                            rel_path = abs_path.relative_to(output_file.parent.parent)
                    except ValueError:
                        rel_path = sf['filename']
                    display_path = str(rel_path) if rel_path else sf['filename']
                    lines.append(f"{j+1}. **{sf['title']}**")
                    lines.append(f"   - 文件名：`{sf['filename']}`")
                    lines.append(f"   - 原始路径：`{sf['path']}`")
                    lines.append("")
            else:
                lines.append("> 无来源文件记录")
                lines.append("")

            lines.append("### 输出文件")
            lines.append("")
            lines.append(f"- 文件名：`{safe_name}.md`")
            if output_file and output_file.exists():
                stat = output_file.stat()
                lines.append(f"- 文件大小：{stat.st_size} 字节")
            lines.append("")
            lines.append("---")
            lines.append("")

        return '\n'.join(lines)

    def _count_words(self, text: str) -> int:
        """统计中文字符数（包含英文单词）"""
        if not text:
            return 0
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        return chinese_chars + english_words

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

