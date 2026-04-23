TOPIC_EXTRACTION_BY_FILENAMES_PROMPT = """你是一位专业的知识整理专家。以下是多个 Markdown 文档的文件名列表，这些文件来自两个文件夹：
- [Organized]：已经整理好的文件
- [Notes]：需要整理的新文件

文件名列表：
{titles}

统计信息：
- Organized 文件夹中的文件数量：{organized_count}
- Notes 文件夹中的文件数量：{notes_count}

请执行以下任务：

1. 分析所有文件名，理解每个文件可能讨论的内容
2. 根据文件名的语义相关性，提取出合适的主题
3. 主题应该具有足够的概括性，能够涵盖多个相关文件
4. 主题之间应互不重叠，边界清晰

{topic_count_instructions}

{output_format_instructions}

注意：
- 请仔细分析每个文件名的语义，不要仅按字面意思分组
- 主题应该具有实际意义，不要为了凑数而创建无意义的主题
- 如果文件名之间关联性不强，可以适当增加主题数量
- 如果文件名之间关联性很强，可以适当减少主题数量（但必须在指定范围内）
- 优先考虑将语义相关的文件名归为同一主题"""


TOPIC_COUNT_SPECIFIED_INSTRUCTIONS = """主题数量要求（必须严格遵守）：
- 必须恰好返回 {topic_count} 个主题
- 不要多返回，也不要少返回"""


OUTPUT_FORMAT_SPECIFIED_INSTRUCTIONS = """输出格式：每行一个主题名称，共 {topic_count} 个，不要编号，不要描述，不要其他任何内容。例如：
机器学习
数据结构
网络协议"""


TOPIC_COUNT_AUTO_INSTRUCTIONS = """主题数量要求（请根据内容选择最优解）：
- 最少 {min_topics} 个主题
- 最多 {max_topics} 个主题
- 请根据文件名的语义相关性，在这个范围内选择最合适的主题数量
- 如果文件名之间关联性很强，可以选择较少的主题数量
- 如果文件名之间关联性较弱，可以选择较多的主题数量"""


OUTPUT_FORMAT_AUTO_INSTRUCTIONS = """输出格式：每行一个主题名称，不要编号，不要描述，不要其他任何内容。例如：
机器学习
数据结构
网络协议"""
