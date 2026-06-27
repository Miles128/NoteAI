# 意图路由与 RAG 实现分析

> 分析对象：NoteAI `python/sidecar/` 与 `webui/js/assistant.js` 中与小忆助手问答相关的意图路由、检索增强生成（RAG）链路。
> 分析时间：2026-06-20

## 1. 整体链路

用户在前端 AI 面板输入问题后，数据流如下：

```
前端 assistant.js
  └── window.api.ragChat(question, topics, tags, currentFile)
        └── Tauri → Python sidecar → RagHandler._rag_chat(params)
              ├── _do_rag_chat_inner
              │     ├── classify_intent(question)      # 意图路由
              │     └── 分支：
              │           ├── chat / general / web  → _answer_without_retrieval（不检索）
              │           ├── action                 → _answer_with_agent（Agent 工具）
              │           └── workspace / unknown    → _answer_with_rag（RAG 检索）
              └── _finish_chat（保存记忆、返回引用）
```

## 2. 意图路由实现细节

### 2.1 入口

- 文件：`python/sidecar/intent_router.py`
- 函数：`classify_intent(question, history)`
- Prompt：`prompts/intent_router.py` / `prompts/yaml/intent_router.yaml` 中的 `INTENT_ROUTER_PROMPT`

### 2.2 意图类别

| 意图 | 后续处理 | 含义 |
|------|---------|------|
| `chat` | `_answer_without_retrieval` | 闲聊、问候、感谢等 |
| `general` | `_answer_without_retrieval` | 通用知识、代码、百科，不依赖本地笔记 |
| `workspace` | `_answer_with_rag` | 询问工作区、笔记、主题、标签、某篇文章 |
| `action` | `_answer_with_agent` | 需要执行操作（移动文件、创建主题等） |
| `web` | `_answer_without_retrieval` | 需要实时网络信息（新闻、天气、股价） |
| `unknown` | `_answer_with_rag` | 无法判断，默认走 RAG |

### 2.3 执行逻辑

1. **空问题** → 直接返回 `unknown`。
2. **快捷规则**：以「你好」「谢谢」「在吗」等开头或等于这些词 → 直接返回 `chat`，跳过大模型调用。
3. **API 配置检查**：未配置 API → 返回 `workspace`（保守走本地检索）。
4. **大模型分类**：调用 `call_llm_raw`，temperature=0.1，要求输出 JSON。
5. **解析兜底**：若模型输出非合法 JSON，默认返回 `workspace`。

### 2.4 存在的核心问题

#### 问题 1：通用知识与本地笔记边界模糊

原始 Prompt 示例把「帮我查一下 Transformer 的原理」标为 `general`。用户实际问「我笔记里 Transformer 相关内容」时，模型很容易因为句式接近而继续判为 `general`，导致不检索本地笔记。

**影响**：用户感觉「明明问的是主题相关内容，却没有引用」。

#### 问题 2：分类完全依赖 LLM，无关键词兜底

除了问候语外，没有基于关键词的兜底规则。如果 LLM 对「工作区」「主题」「标签」「我的笔记」等词不敏感，就会误判。

#### 问题 3：`history` 参数未实际使用

`classify_intent(question, history=...)` 接收了 `history`，但 Prompt 中并未填入。多轮对话里的上下文（例如用户前一句刚问过某主题）无法帮助当前分类。

#### 问题 4：`web` 意图没有真正触发网络搜索

`_answer_without_retrieval` 内部不区分 `general` 和 `web`，都使用 `RAG_ASSISTANT_NO_CONTEXT_PROMPT` 直接让模型回答。即便意图被分为 `web`，也不会真的调用 `duckduckgo_search` / `baidu_search`。

## 3. RAG 检索实现细节

### 3.1 检索开关

- 配置项：`config.rag_enabled`，默认 `true`。
- 当 `rag_enabled=false` 时，`_answer_with_rag` 使用 `sidecar.classic_retriever.retrieve`（主题树 + 全文搜索）。
- 当 `rag_enabled=true` 时，使用 `sidecar.rag.retriever.retrieve`（向量 + BM25 混合检索 + 重排序）。

### 3.2 向量 RAG 检索流程

文件：`python/sidecar/rag/retriever.py`

```
retrieve(query, topics, tags)
  ├── encode_query(query)              # fastembed bge-small-zh-v1.5, 512 维
  ├── hybrid_search(...)               # Milvus Lite 密集 0.7 + 稀疏 0.3
  ├── 若最高分 < 0.33 → HyDE 改写检索
  ├── profile 改写兜底（仅原始无结果时）
  ├── MMR 去重
  ├── bge-reranker-v2-m3 重排序
  ├── filter_usable_chunks
  └── expand_retrieval_context(...)    # 加入主题综述 + 双向链接
```

### 3.3 索引构建

文件：`python/sidecar/rag/retriever.py::rebuild_index`

- 扫描工作区 `.md` 文件，排除 `wiki/`、隐藏文件、`_综述.md`、Raw 等目录。
- 使用 `chunk_file` 按 `##` / `###` 标题切分，最大 1000 字符，重叠约 100~200 字符。
- Chunk ID：`md5("{file_path}::{section_title}::{content[:100]}")[:12]`。
- 生成 Embedding：`BAAI/bge-small-zh-v1.5`（通过 fastembed）。
- 存储：`zvec` 集合 + `bm25s` 索引 + `metadata.json` + `file_manifest.json`。
- 支持增量更新：按文件 mtime/size 判断变更。

### 3.4 Classic 检索（非向量模式）

文件：`python/sidecar/classic_retriever.py`

- 始终注入「主题树」上下文。
- 使用 `utils.fulltext_index`（基于 whoosh 的全文索引）搜索。
- 按 `topics` / `tags` 过滤。
- 加入主题综述（`wiki/` 下的 `_综述.md`）和双向链接内容。

### 3.5 上下文扩展

文件：`python/sidecar/rag/context_expand.py`

- `_survey_items`：根据 topic 找对应综述，最多 2 个主题、每个 2800 字符。
- `_backlink_items`：根据确认的双向链接找相邻文件，最多 4 个、每个 700 字符。

## 4. RAG 回答生成

### 4.1 Prompt

- 文件：`prompts/rag_assistant.py` / `prompts/yaml/rag_assistant.yaml`
- 使用 `RAG_CHAT_PROMPT`：
  - 要求优先根据参考资料回答。
  - 要求用 `[编号]` 标注引用。
  - 结尾输出「【存档建议】是/否」。

### 4.2 引用展示

- 后端将检索结果中的 `source_label`、`file_path`、`topic` 等字段打包为 `citations`。
- 前端 `assistant.js` 的 `_renderCitations` 渲染为可点击的来源列表，点击后调用 `window.api.onFileSelected` 打开文件。

### 4.3 记忆

- 短期记忆：`workspace/.ai_memory/short_memory.json`，保存最近 800 字符的问答摘要。
- 长期记忆：`workspace/.ai_memory/long_memory.json`，从用户消息中提取个人信息。
- 压缩：`_extractive_compress` 取历史前 800 字符，超过 80 字符的句子做首尾摘要 + jieba 关键词。

## 5. Agent 模式

### 5.1 入口

- 文件：`python/sidecar/agent_runner.py`
- 当意图为 `action` 时，由 `_answer_with_agent` 调用 `run_agent_chat`。

### 5.2 工具

| 工具 | 说明 |
|------|------|
| `search_files` | 全文搜索笔记 |
| `list_topics` | 列出主题 |
| `create_topic` | 创建主题（二级需要用户明确指定父主题） |
| `move_file_to_topic` | 移动文件到主题 |
| `run_survey` | 更新主题综述 |
| `start_ingest` | 触发知识库整理 |

### 5.3 限制

- 最多 5 步循环（`MAX_AGENT_STEPS`）。
- 写操作需要用户确认或明确指定上下文。
- 工具结果通过 `AGENT_TOOL_RESULT_PROMPT` 再交给 LLM 生成自然语言回复。

## 6. 已发现并修复的 Bug

| # | 问题 | 位置 | 修复 |
|---|------|------|------|
| 1 | `lastTopicData` / `lastTagsData` 在前端存的是 JSON 字符串，但 `assistant.js` 按对象读取，导致 topics/tags 永远为 `null` | `webui/js/assistant.js` | 提取前 `JSON.parse` |
| 2 | 前端传了 `current_file`，后端 `_answer_with_rag` 未使用 | `python/sidecar/handlers/rag_handler.py` | 读取当前文件内容并作为 `[当前文件]` 前置上下文 |
| 3 | 意图分类 Prompt 对「本地笔记」边界说明不足，容易误判为 `general` | `prompts/intent_router.py` + yaml | 增加明确规则：提到笔记/工作区/主题/标签/文件名必须走 `workspace` |
| 4 | 设置页没有索引状态提示 | `webui/js/settings.js` / `api.js` / `index.html` + 后端 `rag_index_status` | 新增状态接口与 UI，显示是否建立、文件数、片段数、更新时间 |

## 7. 仍存在的问题与风险

### 7.1 设计层

1. **~~RAG 默认关闭~~（已修复：默认开启）**
   - `rag_enabled` 现默认 `true`，新用户开箱即用向量检索。
   - classic 检索仍作为 fallback（用户手动关闭 RAG 时使用）。

2. **索引不会自动建立**
   - 打开工作区后不会自动触发 `init_rag_index`。
   - 用户不知道何时该点「重建索引」。

3. **意图路由过度依赖 LLM**
   - 每个问题都要调一次大模型做分类，增加延迟和费用。
   - 分类错误直接导致不检索或错误检索。

4. **`web` 意图形同虚设**
   - 分类为 `web` 后没有真正调用网络搜索工具，只是让模型用自身知识回答。

### 7.2 实现层

1. **`current_file` 与检索结果可能重复**
   - 修复后虽做了 `seen_paths` 去重，但若当前文件本身在检索结果中，仅跳过内容，编号会不连续。
   - 更合理的做法是给当前文件固定编号 `[0]` 或 `[当前]`，而不是混在 `[1] [2] ...` 中。

2. **`_answer_with_rag` 不区分 `workspace` 和 `unknown`**
   - 两者走同一条路径，但 `unknown` 的问题可能更适合先用 LLM 澄清。

3. **引用编号与 Prompt 要求不一致**
   - Prompt 要求模型用 `[编号]` 引用，但当前文件被标记为 `[当前文件]`，模型可能无法正确引用。

4. **短期记忆压缩简单粗暴**
   - `_extractive_compress` 只取前 800 字符，长对话中较早的关键信息会丢失。
   - 没有按主题或重要性做摘要。

5. **错误状态冷却机制**
   - `_check_error_reset` 会在 180 秒内阻止再次请求，但只对同一进程有效，sidecar 重启后失效。
   - 错误信息直接展示给用户，缺乏更友好的重试引导。

6. **检索缓存无过期**
   - `retriever.py` 有 `_query_cache`，但只按 LRU 淘汰，没有按时间过期，工作区内容更新后可能返回旧结果。

7. **classic 检索的 `topic` 字段兼容问题**
   - `classic_retriever.py` 中 frontmatter 的 `topic` 既可能是字符串也可能是列表，代码有兼容处理，但 ` RagHandler._answer_with_rag` 中没有类似兼容，若 `params.get("topics")` 收到嵌套列表会原样传给检索函数。

8. **`rag_index_status` 只读 manifest**
   - 若 manifest 与真实 collection 不一致（例如手动删除文件），状态会显示错误。

### 7.3 测试与可观测性

1. **缺少意图路由的单元测试**
   - `classify_intent` 依赖 LLM，难以单元测试，但可以增加关键词兜底规则的测试。

2. **RAG 链路端到端测试有限**
   - `tests/integration/test_rag_pipeline.py` 有测试，但多为 happy path。
   - 缺少「意图分类错误导致不检索」「current_file 上下文生效」等回归测试。

3. **检索结果不可见**
   - 用户看不到实际检索到了哪些片段，只能看到最终引用，调试困难。

## 8. 改进建议

### 8.1 短期（低风险）

1. **默认开启 RAG 或首次引导**
   - 首次设置工作区后弹出提示：「是否为小忆建立知识库索引？」
   - 或在设置页增加醒目提示「向量 RAG 未开启」。

2. **意图路由增加关键词规则**
   - 在 LLM 之前增加确定性规则：包含「我的笔记」「工作区」「某主题」「某标签」「某文件」等关键词直接判 `workspace`。

3. **真正支持 `web` 意图**
   - 在 `_answer_without_retrieval` 中根据 `intent` 调用 `duckduckgo_search` / `baidu_search`，并使用 `RAG_ASSISTANT_WEB_PROMPT`。

4. **当前文件引用规范化**
   - 给当前文件固定编号 `[0]`，并在 Prompt 中明确说明 `[0]` 为当前打开文件。

### 8.2 中期（中等风险）

1. **自动增量索引**
   - 文件监听（已有 watchdog）触发 `incremental_update`，保持索引实时同步。

2. **检索结果调试面板**
   - 在设置或 AI 面板增加「显示检索片段」开关，方便排查召回问题。

3. **多轮对话记忆改进**
   - 使用 LLM 对历史做主题级摘要，而不是简单截断。

4. **意图路由可配置**
   - 允许用户在设置中选择「默认检索本地笔记」或「默认通用回答」，减少分类错误的影响。

### 8.3 长期（架构级）

1. **统一检索抽象**
   - 将 classic 和 vector RAG 抽象为同一 `Retriever` 接口，支持按问题类型动态选择策略。

2. **引入 ReAct / Plan-and-Execute**
   - 对复杂问题让 Agent 先规划再检索，而不是单轮 RAG。

3. **引用溯源到段落**
   - 当前引用只能定位到文件，未来可定位到具体段落或句子。

## 9. 结论

当前实现已经覆盖了一条完整的「意图路由 → RAG 检索 → 引用回答」链路，但在**默认开关、意图分类鲁棒性、当前文件上下文、索引状态可见性**等方面存在明显体验问题。本次已修复的 4 个 bug 解决了最直接影响用户感知的缺陷，但仍有较多优化空间，特别是让 RAG 真正「开箱即用」和降低 LLM 分类错误率。
