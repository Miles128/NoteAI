"""
多智能体框架模块 —— 基于多角色协作的文档处理工作流。

未使用说明：
    本模块为 agents/ 模块链的核心入口，与 agents/base.py、
    agents/context_manager.py、agents/semantic_chunker.py 共同构成
    一套多智能体协作式文档处理框架。
    该框架目前没有任何调用方，处于保留状态。

框架设计：
    - WorkerAgent: 单角色执行器（EXTRACTOR/SUMMARIZER/INTEGRATOR/REWRITER）
    - CoordinatorAgent: 任务协调器，负责管理整个处理流程的生命周期
    - SemanticChunker: 语义分块器（来自 agents/semantic_chunker.py）
    - ContextManager: 跨块上下文管理器（来自 agents/context_manager.py）

工作流程：
    文档 → 分块 → EXTRACTOR 提取 → SUMMARIZER 摘要
         → INTEGRATOR 整合 → REWRITER 重写 → 最终输出

启用方式：
    在需要时，直接实例化 CoordinatorAgent 并调用 process() 方法即可。
    当前 note_integration.py 使用的是另一套基于单一 LLM 的整合流程，
    若需要更细粒度的多角色协作，可切换至本框架。
"""

import time
import json
import hashlib
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base import (
    AgentRole, TaskStatus, AgentTask, Chunk,
    ProcessingResult, CrossChunkContext, MessageBus
)
from agents.semantic_chunker import SemanticChunker, ChunkConfig
from agents.context_manager import ContextManager
from config.settings import config
from prompts import (
    EXTRACTOR_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
    INTEGRATOR_SYSTEM_PROMPT,
    REWRITER_SYSTEM_PROMPT
)


WORKER_SYSTEM_PROMPTS = {
    AgentRole.EXTRACTOR: EXTRACTOR_SYSTEM_PROMPT,
    AgentRole.SUMMARIZER: SUMMARIZER_SYSTEM_PROMPT,
    AgentRole.INTEGRATOR: INTEGRATOR_SYSTEM_PROMPT,
    AgentRole.REWRITER: REWRITER_SYSTEM_PROMPT,
}


class WorkerAgent:
    """
    单角色执行器。

    职责：
        根据指定的 AgentRole，从 MessageBus 中拉取对应 chunk 的内容，
        结合 ContextManager 的跨块上下文，构建完整 prompt 后调用 LLM，
        并将结果回写到 ContextManager。

    参数：
        agent_id: 该 worker 的唯一标识
        role: 扮演的角色（EXTRACTOR/SUMMARIZER/INTEGRATOR/REWRITER）
        message_bus: MessageBus 实例，用于获取块内容
    """

    def __init__(self, agent_id: str, role: AgentRole, message_bus: MessageBus):
        self.agent_id = agent_id
        self.role = role
        self.message_bus = message_bus
        self.system_prompt = WORKER_SYSTEM_PROMPTS.get(role, "")

    def process(self, task: AgentTask, context: ContextManager) -> Dict:
        """
        执行单个任务。

        参数：
            task: AgentTask 实例，包含 chunk_ids、instruction 等
            context: ContextManager 实例，用于获取跨块上下文

        返回：
            任务执行结果字典，格式因 role 不同而异：
            - EXTRACTOR: {summary, entities, key_points, open_questions}
            - SUMMARIZER: {summary}
            - INTEGRATOR: {integrated}
            - REWRITER: {rewritten}
            - 出错时: {error: str}
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import PromptTemplate

        llm = ChatOpenAI(
            api_key=config.api_key,
            base_url=config.api_base,
            model=config.model_name,
            temperature=0.3,
            max_tokens=config.max_tokens
        )

        all_content = []
        for chunk_id in task.chunk_ids:
            msg = self.message_bus.get_messages(topic=f"chunk_{chunk_id}")
            for m in msg:
                if 'content' in m.get('data', {}):
                    all_content.append(m['data']['content'])
                    break

        combined_content = "\n---\n".join(all_content)
        cross_context = context.build_context_prompt(task.chunk_ids[0] if task.chunk_ids else "")

        if cross_context:
            full_input = f"""=== 上下文背景（前文摘要和实体信息）===
{cross_context}

=== 待处理内容 ===
{combined_content}

=== 任务 ===
{task.instruction}"""
        else:
            full_input = f"""=== 待处理内容 ===
{combined_content}

=== 任务 ===
{task.instruction}"""

        try:
            if self.role == AgentRole.EXTRACTOR:
                prompt = PromptTemplate(
                    template=self.system_prompt + "\n\n{full_input}",
                    input_variables=["full_input"]
                )
                chain = prompt.pipe(llm)
                response = chain.invoke({"full_input": full_input})
                result = json.loads(response.content)
                context.add_chunk_processed(
                    task.chunk_ids[0] if task.chunk_ids else "",
                    result.get("summary", ""),
                    result.get("entities", [])
                )
                return result

            elif self.role == AgentRole.SUMMARIZER:
                prompt = PromptTemplate(
                    template=self.system_prompt + "\n\n{full_input}",
                    input_variables=["full_input"]
                )
                chain = prompt.pipe(llm)
                response = chain.invoke({"full_input": full_input})
                return {"summary": response.content}

            elif self.role == AgentRole.INTEGRATOR:
                prompt = PromptTemplate(
                    template=self.system_prompt + "\n\n{full_input}",
                    input_variables=["full_input"]
                )
                chain = prompt.pipe(llm)
                response = chain.invoke({"full_input": full_input})
                return {"integrated": response.content}

            elif self.role == AgentRole.REWRITER:
                prompt = PromptTemplate(
                    template=self.system_prompt + "\n\n{full_input}",
                    input_variables=["full_input"]
                )
                chain = prompt.pipe(llm)
                response = chain.invoke({"full_input": full_input})
                return {"rewritten": response.content}

        except Exception as e:
            return {"error": str(e)}


class CoordinatorAgent:
    """
    任务协调器。

    职责：
        管理整个多智能体工作流的生命周期，包括：
        1. 文档加载与分块
        2. 阶段式任务调度（提取 → 摘要 → 整合 → 重写）
        3. 进度上报
        4. 最终结果组装

    使用方式：
        coordinator = CoordinatorAgent(progress_callback=my_callback)
        result = coordinator.process(documents=[{"title": "...", "content": "..."}])
        print(result.final_content)
    """

    def __init__(self, progress_callback: Optional[Callable] = None):
        """
        初始化协调器。

        参数：
            progress_callback: 进度回调函数，签名为 (current, total, message, extra)
        """
        self.progress_callback = progress_callback
        self.message_bus = MessageBus()
        self.context_manager = ContextManager()
        self.chunker = SemanticChunker()
        self.chunks: Dict[str, Chunk] = {}
        self.tasks: List[AgentTask] = []
        self.worker_pool: Dict[AgentRole, WorkerAgent] = {}

        for role in [AgentRole.EXTRACTOR, AgentRole.SUMMARIZER,
                     AgentRole.INTEGRATOR, AgentRole.REWRITER]:
            self.worker_pool[role] = WorkerAgent(
                f"worker_{role.value}",
                role,
                self.message_bus
            )

    def process(self, documents: List[Dict], save_path: str = None) -> ProcessingResult:
        """
        执行完整的文档处理工作流。

        参数：
            documents: 文档列表，每项为 {title: str, content: str} 结构
            save_path: 可选，输出文件的保存目录路径

        返回：
            ProcessingResult 实例，包含最终内容和各项统计信息
        """
        start_time = time.time()
        result = ProcessingResult()
        self._start_time = start_time

        self._report_progress(0, 1, "开始多智能体整合处理...")

        all_chunks = self._load_and_chunk_documents(documents, result)
        if not all_chunks:
            result.errors.append("分块失败：没有生成任何文本块")
            return result

        self._report_progress(0.1, 1, f"分块完成：共 {len(all_chunks)} 个块")

        self._process_extraction(all_chunks)
        self._report_progress(0.3, 1, "提取完成")

        self._process_summarization()
        self._report_progress(0.5, 1, "摘要完成")

        self._process_integration()
        self._report_progress(0.7, 1, "整合完成")

        self._process_rewrite()
        self._report_progress(0.9, 1, "重写完成")

        result.final_content = self._assemble_final_result()
        result.processing_time = time.time() - start_time

        self._report_progress(1.0, 1, "处理完成")

        if save_path:
            from pathlib import Path
            output_file = Path(save_path) / "多智能体整合结果.md"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(result.final_content, encoding='utf-8')
            result.file_path = str(output_file)

        return result

    def _load_and_chunk_documents(self, documents: List[Dict], result: ProcessingResult) -> List[Chunk]:
        """对输入文档进行语义分块，并将每块发布到 MessageBus"""
        result.original_doc_count = len(documents)
        all_chunks = []

        for doc in documents:
            chunks = self.chunker.chunk_document(
                doc.get('content', ''),
                doc.get('title', '')
            )
            for chunk in chunks:
                self.chunks[chunk.id] = chunk
                all_chunks.append(chunk)
                self.message_bus.publish(f"chunk_{chunk.id}", {
                    "content": chunk.content,
                    "title": chunk.title,
                    "chunk_type": chunk.chunk_type
                })

        result.total_chunks = len(all_chunks)
        return all_chunks

    def _process_extraction(self, chunks: List[Chunk]):
        """阶段1：为每个 chunk 创建 EXTRACTOR 任务并同步执行"""
        for i, chunk in enumerate(chunks):
            if self.progress_callback and (i + 1) % 10 == 0:
                self.progress_callback(i + 1, len(chunks), f"提取进度: {i+1}/{len(chunks)}", 0.2)

            task = AgentTask(
                task_id=f"extract_{chunk.id}",
                role=AgentRole.EXTRACTOR,
                chunk_ids=[chunk.id],
                instruction=f"提取此文本块的核心信息：{chunk.title}"
            )
            self.tasks.append(task)
            self._execute_task_sync(task)

    def _process_summarization(self):
        """阶段2：将已提取的块批量委托给 SUMMARIZER 进行压缩"""
        extractor_tasks = [t for t in self.tasks if t.role == AgentRole.EXTRACTOR
                         and t.status == TaskStatus.COMPLETED]

        batch_size = 5
        for i in range(0, len(extractor_tasks), batch_size):
            batch = extractor_tasks[i:i+batch_size]
            batch_ids = [t.chunk_ids[0] for t in batch]

            task = AgentTask(
                task_id=f"summarize_batch_{i//batch_size}",
                role=AgentRole.SUMMARIZER,
                chunk_ids=batch_ids,
                instruction="压缩以下内容，保留所有核心信息"
            )
            self.tasks.append(task)
            self._execute_task_sync(task)

    def _process_integration(self):
        """阶段3：将摘要批次委托给 INTEGRATOR 进行整合"""
        summarizer_tasks = [t for t in self.tasks if t.role == AgentRole.SUMMARIZER
                           and t.status == TaskStatus.COMPLETED]

        all_summaries = []
        for task in summarizer_tasks:
            if task.result and 'summary' in task.result:
                all_summaries.append(task.result['summary'])

        batch_size = config.max_context_tokens // 400
        for i in range(0, len(all_summaries), batch_size):
            batch = all_summaries[i:i+batch_size]
            batch_chunks = []
            for st in summarizer_tasks[i:i+batch_size]:
                batch_chunks.extend(st.chunk_ids)

            task = AgentTask(
                task_id=f"integrate_batch_{i//batch_size}",
                role=AgentRole.INTEGRATOR,
                chunk_ids=batch_chunks,
                instruction="将以下摘要整合为一个结构清晰、逻辑连贯的内容"
            )
            self.tasks.append(task)
            self._execute_task_sync(task)

    def _process_rewrite(self):
        """阶段4：为每个整合结果创建 REWRITER 任务进行文字优化"""
        integrator_tasks = [t for t in self.tasks if t.role == AgentRole.INTEGRATOR
                          and t.status == TaskStatus.COMPLETED]

        for task in integrator_tasks:
            rewrite_task = AgentTask(
                task_id=f"rewrite_{task.task_id}",
                role=AgentRole.REWRITER,
                chunk_ids=task.chunk_ids,
                instruction="优化以下内容的表达方式，提升可读性"
            )
            self.tasks.append(rewrite_task)
            self._execute_task_sync(rewrite_task)

    def _execute_task_sync(self, task: AgentTask):
        """同步执行单个任务并更新状态"""
        task.status = TaskStatus.RUNNING
        worker = self.worker_pool.get(task.role)
        if not worker:
            task.status = TaskStatus.FAILED
            task.error = f"No worker for role {task.role}"
            return

        try:
            result = worker.process(task, self.context_manager)
            task.result = result
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)

    def _assemble_final_result(self) -> str:
        """将所有 REWRITER 的输出组装为最终 Markdown 文档"""
        rewrite_tasks = [t for t in self.tasks if t.role == AgentRole.REWRITER
                       and t.status == TaskStatus.COMPLETED]

        sections = []
        for task in rewrite_tasks:
            if task.result and 'rewritten' in task.result:
                sections.append(task.result['rewritten'])

        if not sections:
            integrator_results = [t.result.get('integrated', '')
                               for t in self.tasks if t.role == AgentRole.INTEGRATOR
                               and t.status == TaskStatus.COMPLETED]
            sections = integrator_results

        final = "# 多智能体整合结果\n\n"
        final += f"*由 {len(self.chunks)} 个智能体协作生成*\n\n"
        final += "---\n\n"
        final += "\n\n".join(sections)
        final += "\n\n---\n\n"
        final += f"*处理 {len(self.chunks)} 个文本块，耗时 {time.time() - self._start_time:.1f}秒*" if hasattr(self, '_start_time') else ""

        return final

    def _report_progress(self, current: int, total: int, message: str):
        """调用进度回调，传递 (current, total, message, extra=1.0)"""
        if self.progress_callback:
            self.progress_callback(current, total, message, 1.0)

    def get_processing_stats(self) -> Dict:
        """
        获取处理统计信息。

        返回：
            包含总块数、总任务数、上下文统计、各角色任务完成情况的字典
        """
        stats = {
            "total_chunks": len(self.chunks),
            "total_tasks": len(self.tasks),
            "context_stats": self.context_manager.get_statistics(),
            "tasks_by_role": {}
        }
        for role in AgentRole:
            role_tasks = [t for t in self.tasks if t.role == role]
            stats["tasks_by_role"][role.value] = {
                "total": len(role_tasks),
                "completed": sum(1 for t in role_tasks if t.status == TaskStatus.COMPLETED),
                "failed": sum(1 for t in role_tasks if t.status == TaskStatus.FAILED)
            }
        return stats
