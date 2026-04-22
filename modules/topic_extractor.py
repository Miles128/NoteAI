"""
主题提取模块
负责从 Notes 和 Organized 文件夹中提取主题
"""

from pathlib import Path
from typing import List, Dict, Optional, Tuple
from config.settings import config
from utils.logger import logger
from utils.helpers import check_api_config


class TopicExtractor:
    """主题提取器
    
    功能：
    1. 从 Notes 和 Organized 文件夹中读取 MD 文件名
    2. 将文件名发送给大模型，让大模型返回主题列表
    3. 支持指定主题个数，或让大模型从范围中选择最优解
    """
    
    def __init__(self, progress_callback=None):
        """
        初始化主题提取器
        
        Args:
            progress_callback: 进度回调函数，接收 (current, total, message) 参数
        """
        self.progress_callback = progress_callback
        self.notes_folder = config.get_notes_folder()
        self.organized_folder = config.get_organized_folder()
    
    def _update_progress(self, current: int, total: int, message: str):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    def get_md_filenames(self, folder_path: str) -> List[str]:
        """
        获取文件夹下所有 MD 文件名（不读取内容）
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            文件名列表（不含后缀）
        """
        filenames = []
        folder = Path(folder_path)
        
        if not folder.exists():
            return filenames
        
        for md_file in folder.rglob("*.md"):
            if not md_file.name.startswith('.'):
                filenames.append(md_file.stem)
        
        return filenames
    
    def calculate_topic_range(self, notes_count: int, organized_count: int) -> Tuple[int, int]:
        """
        计算主题个数范围
        
        如果没有指定主题个数，让大模型从以下范围中选择：
        - 下限：organized 文件夹里文件的个数
        - 上限：organized 文件夹里文件的个数 + notes 文件夹下文件数量的 1/2
        
        Args:
            notes_count: Notes 文件夹中的文件数量
            organized_count: Organized 文件夹中的文件数量
            
        Returns:
            (min_topics, max_topics) 主题个数范围
        """
        min_topics = max(organized_count, 2)
        max_topics = max(organized_count + int(notes_count / 2), min_topics + 1)
        
        # 确保至少有 2 个主题
        min_topics = max(min_topics, 2)
        max_topics = max(max_topics, min_topics + 1)
        
        return min_topics, max_topics
    
    def extract_topics(self, specified_topic_count: Optional[int] = None) -> Dict:
        """
        提取主题
        
        流程：
        1. 读取 Notes 和 Organized 文件夹下所有 MD 文件名
        2. 计算主题个数范围（如果没有指定）
        3. 将文件名和主题个数范围发送给大模型
        4. 解析大模型返回的主题列表
        
        Args:
            specified_topic_count: 用户指定的主题个数，如果为 None 则让大模型从范围中选择
            
        Returns:
            包含 success、topics、error 等信息的字典
        """
        try:
            # 检查工作区是否设置
            if not config.is_workspace_set():
                return {"success": False, "error": "请先设置工作文件夹"}
            
            # 检查 API 配置
            is_valid, error_msg = check_api_config()
            if not is_valid:
                return {"success": False, "error": f"API 配置无效: {error_msg}"}
            
            self._update_progress(1, 10, "正在读取文件列表...")
            
            # 获取 Notes 文件夹中的文件名
            notes_filenames = self.get_md_filenames(self.notes_folder)
            notes_count = len(notes_filenames)
            
            # 获取 Organized 文件夹中的文件名
            organized_filenames = self.get_md_filenames(self.organized_folder)
            organized_count = len(organized_filenames)
            
            if notes_count == 0 and organized_count == 0:
                return {"success": False, "error": "Notes 和 Organized 文件夹中都没有 Markdown 文件"}
            
            self._update_progress(2, 10, f"找到 {notes_count} 个 Notes 文件，{organized_count} 个 Organized 文件")
            
            # 计算主题个数范围
            if specified_topic_count is None or specified_topic_count <= 0:
                min_topics, max_topics = self.calculate_topic_range(notes_count, organized_count)
                is_specified = False
            else:
                min_topics = specified_topic_count
                max_topics = specified_topic_count
                is_specified = True
            
            self._update_progress(3, 10, f"主题个数范围: {min_topics} - {max_topics}")
            
            # 构建文件名列表文本
            all_filenames = []
            if organized_filenames:
                all_filenames.extend([f"[Organized] {name}" for name in organized_filenames])
            if notes_filenames:
                all_filenames.extend([f"[Notes] {name}" for name in notes_filenames])
            
            titles_text = '\n'.join([f"{i+1}. {name}" for i, name in enumerate(all_filenames)])
            
            self._update_progress(4, 10, "正在调用大模型分析主题...")
            
            # 根据是否指定主题个数生成不同的提示词
            if is_specified:
                # 用户指定了主题个数
                topic_count_instructions = f"""主题数量要求（必须严格遵守）：
- 必须恰好返回 {min_topics} 个主题
- 不要多返回，也不要少返回"""
                output_format_instructions = f"""输出格式（每行一个主题，共 {min_topics} 个）：
主题1：名称 | 描述
主题2：名称 | 描述
...
主题{min_topics}：名称 | 描述"""
            else:
                # 用户没有指定主题个数，让大模型从范围中选择最优解
                topic_count_instructions = f"""主题数量要求（请根据内容选择最优解）：
- 最少 {min_topics} 个主题
- 最多 {max_topics} 个主题
- 请根据文件名的语义相关性，在这个范围内选择最合适的主题数量
- 如果文件名之间关联性很强，可以选择较少的主题数量
- 如果文件名之间关联性较弱，可以选择较多的主题数量
- 请在输出中说明你选择的主题数量的理由"""
                output_format_instructions = """输出格式：
首先，请用一句话说明你选择的主题数量以及理由。

然后，按以下格式输出主题列表（每行一个主题）：
主题1：名称 | 描述
主题2：名称 | 描述
...

或者，你也可以使用 JSON 格式输出：
{
    "topic_count": 实际选择的主题数量,
    "reason": "选择理由",
    "topics": [
        {"name": "主题名称", "description": "主题描述"},
        ...
    ]
}"""
            
            # 构建最终提示词
            from prompts.note_integration import TOPIC_EXTRACTION_BY_FILENAMES_PROMPT
            
            final_prompt = TOPIC_EXTRACTION_BY_FILENAMES_PROMPT.format(
                titles=titles_text,
                topic_count_instructions=topic_count_instructions,
                output_format_instructions=output_format_instructions,
                notes_count=notes_count,
                organized_count=organized_count
            )
            
            # 调用大模型
            from langchain_openai import ChatOpenAI
            
            llm = ChatOpenAI(
                api_key=config.api_key,
                base_url=config.api_base,
                model=config.model_name,
                temperature=0.5,
                max_tokens=config.max_tokens
            )
            
            response = llm.invoke(final_prompt)
            
            content = response.content.strip()
            
            self._update_progress(7, 10, "正在解析主题结果...")
            
            # 解析主题列表
            topics = self._parse_topics_response(content)
            
            if not topics:
                return {"success": False, "error": "LLM 未返回有效主题"}
            
            self._update_progress(10, 10, f"成功提取 {len(topics)} 个主题")
            
            logger.info(f"提取了 {len(topics)} 个主题: {topics}")
            
            return {
                "success": True,
                "topics": topics,
                "topic_count": len(topics),
                "min_topics": min_topics,
                "max_topics": max_topics,
                "is_specified": is_specified,
                "notes_count": notes_count,
                "organized_count": organized_count
            }
            
        except Exception as e:
            logger.error(f"提取主题失败: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"提取主题失败: {str(e)}"}
    
    def _parse_topics_response(self, content: str) -> List[str]:
        """
        解析大模型返回的主题列表
        
        支持多种格式：
        1. "主题1：名称 | 描述" 格式
        2. "1. 名称" 格式
        3. JSON 格式
        
        Args:
            content: 大模型返回的内容
            
        Returns:
            主题名称列表
        """
        topics = []
        
        # 尝试解析 JSON 格式
        try:
            import json
            data = json.loads(content)
            if isinstance(data, dict) and 'topics' in data:
                for item in data['topics']:
                    if isinstance(item, dict) and 'name' in item:
                        topics.append(item['name'])
                    elif isinstance(item, str):
                        topics.append(item)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and 'name' in item:
                        topics.append(item['name'])
                    elif isinstance(item, str):
                        topics.append(item)
            
            if topics:
                return topics
        except json.JSONDecodeError:
            pass
        
        # 尝试解析文本格式
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # 格式："主题1：名称 | 描述" 或 "主题1: 名称 | 描述"
            if '|' in line:
                name = line.split('|')[0].strip()
                # 移除 "主题X：" 或 "主题X:" 前缀
                name = self._remove_topic_prefix(name)
                if name:
                    topics.append(name)
            else:
                # 格式："1. 名称" 或 "- 名称"
                name = self._remove_number_prefix(line)
                name = self._remove_topic_prefix(name)
                if name:
                    topics.append(name)
        
        return topics
    
    def _remove_topic_prefix(self, text: str) -> str:
        """移除 "主题X：" 或 "主题X:" 前缀"""
        import re
        # 匹配 "主题1："、"主题1:"、"主题123：" 等格式
        text = re.sub(r'^主题\d+[：:]\s*', '', text).strip()
        return text
    
    def _remove_number_prefix(self, text: str) -> str:
        """移除数字前缀，如 "1. "、"2、"、"- " 等"""
        import re
        # 匹配 "1. "、"2、"、"3) "、"- "、"• " 等格式
        text = re.sub(r'^[\d\-\•\*]+[\.\、\)\s]+\s*', '', text).strip()
        return text
