# 笔记整合模块重构设计

**日期：** 2026-04-16
**版本：** v1.0

---

## 一、目标

对 `NoteIntegration` 类进行系统性重构，建立基于 Heading 拆分和主题驱动的笔记整合流程，替代原有的 RAG 向量检索方案。

---

## 二、整体流程

```
输入文件
    │
    ▼
┌─────────────────────────────────────────┐
│ 第一步：提取标题 + Heading 拆分           │
│  - documents: [{title, path, filename}] │
│  - chunks: [{chunk_id, doc_id, content, │
│              word_count, source_order}] │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 第二步：主题提取 + 块归属映射              │
│  - 输入：documents.titles + chunks      │
│  - 输出：topics + topic_chunk_mapping   │
│  - 主题数量 >= ceil(总字数/LLM最大输入)  │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 第三步：主题内容处理                       │
│  - 按 source_order 拼接关联 chunks      │
│  - 计算总字数 vs 阈值(90%)              │
│  - 超限：每个 chunk 单独压缩后合并       │
│  - LLM 生成主题笔记（保持原篇幅）         │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 第四步：输出独立文件                      │
│  每个主题生成独立的 .md 文件             │
└─────────────────────────────────────────┘
```

---

## 三、第一步：提取标题 + Heading 拆分

### 3.1 输入

文件夹路径

### 3.2 输出

```python
documents = [
    {"title": "Python基础", "path": "/path/to/python.md", "filename": "python.md"},
    {"title": "机器学习入门", "path": "/path/to/ml.md", "filename": "ml.md"},
]

chunks = [
    {
        "chunk_id": "chunk_0",
        "doc_id": 0,
        "content": "## Python基础\n\nPython是一种高级编程语言...",
        "word_count": 350,
        "source_order": 0
    },
    {
        "chunk_id": "chunk_1",
        "doc_id": 0,
        "content": "## Python数据类型\n\nPython支持多种数据类型...",
        "word_count": 420,
        "source_order": 1
    },
    {
        "chunk_id": "chunk_2",
        "doc_id": 1,
        "content": "## 机器学习概述\n\n机器学习是人工智能的分支...",
        "word_count": 380,
        "source_order": 0
    },
]
```

### 3.3 拆分规则

1. 按 Markdown Heading (`##`、`###`) 拆分
2. 每个 chunk 保留完整的 Heading 标题 + 内容
3. 拆分后的每个 chunk 字数范围：**100-500 字**
4. 如果单个 Heading 内容超过 500 字：按子段落继续拆分
5. 如果单个 Heading 内容小于 100 字：合并到前一个 chunk
6. `source_order` 记录该 chunk 在原始文件中的顺序

---

## 四、第二步：主题提取 + 块归属映射

### 4.1 输入

- `documents` 的 `title` 列表
- `chunks` 列表（用于 LLM 理解主题覆盖范围）

### 4.2 提示词模板

```python
TOPIC_EXTRACTION_PROMPT = """
你是一位专业的知识整理专家。以下是多个Markdown文档的标题：

{titles}

这些文档的内容已被拆分为多个块（每个块以标题开头）：
{chunks_info}

请执行以下任务：

1. 分析所有文档标题和内容块，提取主要主题
2. 确保主题数量不少于 {min_topic_count} 个
3. 每个主题需要关联其对应的内容块

主题数量计算规则：总字数 {total_words} / LLM最大输入 {max_input} = {required_topics}，向上取整

请以以下JSON格式输出：
{{
    "topics": [
        {{"name": "主题名称", "description": "主题描述"}},
        ...
    ],
    "topic_chunk_mapping": {{
        "主题名称": ["chunk_id_1", "chunk_id_2", ...],
        ...
    }}
}}

注意：
- 每个chunk可以归属多个主题
- 主题名称应简洁明了
- 确保所有主题的知识完整性
"""
```

### 4.3 输出

```python
{
    "topics": [
        {"name": "Python", "description": "Python编程语言基础和特性"},
        {"name": "机器学习", "description": "机器学习基本概念和算法"}
    ],
    "topic_chunk_mapping": {
        "Python": ["chunk_0", "chunk_1"],
        "机器学习": ["chunk_2", "chunk_3"]
    }
}
```

### 4.4 主题数量保障

```python
min_topic_count = ceil(total_words / max_input)
```

---

## 五、第三步：主题内容处理

### 5.1 对每个主题的处理流程

```python
def process_topic(topic_name, chunk_ids, chunks):
    # Step 1: 收集关联模块
    topic_chunks = [c for c in chunks if c["chunk_id"] in chunk_ids]

    # Step 2: 按 source_order 排序并拼接
    topic_chunks.sort(key=lambda x: x["source_order"])
    concatenated_content = "\n\n".join([c["content"] for c in topic_chunks])
    original_word_count = sum(c["word_count"] for c in topic_chunks)

    # Step 3: 判断是否需要压缩
    threshold = config.max_tokens * 0.9  # 90% 阈值

    if original_word_count > threshold:
        # 需要压缩：计算压缩比例
        compression_ratio = threshold / original_word_count

        # Step 4: 每个 chunk 单独压缩
        compressed_chunks = []
        for chunk in topic_chunks:
            compressed = compress_chunk(chunk, compression_ratio)
            compressed_chunks.append(compressed)

        # Step 5: 拼接压缩后的内容
        final_input = "\n\n".join([c["content"] for c in compressed_chunks])

        # Step 6: LLM 生成，指示补齐到原篇幅
        result = generate_topic_note(
            topic_name,
            final_input,
            target_word_count=original_word_count
        )
    else:
        # 不需要压缩，直接生成
        result = generate_topic_note(
            topic_name,
            concatenated_content,
            target_word_count=original_word_count
        )

    return result
```

### 5.2 Chunk 压缩方法

```python
COMPRESSION_PROMPT = """
你是一位专业的知识编辑。以下是关于某个主题的Markdown内容块：

{original_content}

由于上下文长度限制，需要将此内容压缩至约 {target_ratio:.0%} 的篇幅。

请执行以下操作：
1. 理解该内容块的核心知识点和逻辑结构
2. 保留所有关键概念、定义、结论
3. 对于详细的举例、解释性文字可以精简
4. 保持Markdown格式结构不变

输出压缩后的完整内容。
"""
```

### 5.3 主题笔记生成方法

```python
GENERATION_PROMPT = """
你是一位专业的知识整理专家。请基于以下内容，为主题「{topic_name}」撰写一篇结构清晰、内容详实的Markdown笔记。

原始内容：
{content}

要求：
1. 最终内容篇幅应与原始内容相近（约 {target_word_count} 字）
2. 保持Markdown格式，使用合理的标题层级
3. 内容应当精炼且系统化
4. 保留所有核心知识点和关键信息

请直接输出整理后的笔记内容。
"""
```

---

## 六、第四步：输出

每个主题生成独立的 Markdown 文件：

```
/输出目录/
  ├── Python.md
  ├── 机器学习.md
  └── ...
```

文件内容格式：

```markdown
# Python

Python是一种高级编程语言...

## 基础语法

...

## 数据类型

...
```

---

## 七、关键数据结构

### 7.1 Chunk 结构

```python
@dataclass
class Chunk:
    chunk_id: str          # 唯一标识
    doc_id: int            # 所属文档索引
    content: str           # 完整内容（含Heading）
    word_count: int        # 字数统计
    source_order: int      # 原始顺序
```

### 7.2 Topic 结构

```python
@dataclass
class Topic:
    name: str                    # 主题名称
    description: str             # 主题描述
    chunk_ids: List[str]         # 关联的chunk_id列表
```

### 7.3 处理结果结构

```python
@dataclass
class TopicResult:
    topic_name: str              # 主题名称
    content: str                 # 生成的内容
    source_chunks: List[str]     # 来源chunk_id列表
    was_compressed: bool         # 是否经过压缩
    original_word_count: int      # 原始字数
    final_word_count: int         # 最终字数
```

---

## 八、新增/修改的方法

| 方法名 | 功能 | 位置 |
|--------|------|------|
| `_split_documents_by_heading()` | 对文档列表按Heading拆分 | 新增 |
| `_count_words()` | 统计中文字符数 | 新增 |
| `_extract_topics_with_mapping()` | LLM提取主题和块归属 | 新增 |
| `_compress_chunk()` | 单个chunk的LLM压缩 | 新增 |
| `_generate_topic_note()` | 生成主题笔记 | 新增 |
| `_process_topic()` | 主题内容处理主逻辑 | 新增 |
| `integrate()` | 统一入口（修改） | 修改 |

---

## 九、Prompt 清单

1. `TOPIC_EXTRACTION_PROMPT` - 主题提取和块归属映射
2. `CHUNK_COMPRESSION_PROMPT` - 单个chunk压缩
3. `TOPIC_NOTE_GENERATION_PROMPT` - 主题笔记生成

---

## 十、错误处理

| 场景 | 处理方式 |
|------|----------|
| LLM API 调用失败 | 记录日志，抛出 `NetworkError` |
| 解析 JSON 失败 | 回退到简单标题匹配 |
| chunk 压缩失败 | 使用原始 chunk 内容继续处理 |
| 主题笔记生成失败 | 生成基础结构，标注失败信息 |
