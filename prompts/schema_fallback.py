"""Workspace schema fallback template prompt."""

SCHEMA_FALLBACK_PROMPT = """# NoteAI 工作区 Schema — 四海

> 本工作区知识库宪法。个人画像见 `.ai_memory/user_profile.json`（设置 → 用户画像）。

## 1. 定位

AI 知识编译器：采集 → 主题整理 → wiki 综述编译 → RAG 问答。侧重 AI 产品、Agent、RAG、大模型应用。中文优先、简洁技术向。

## 2. 目录

| 路径 | 角色 |
|------|------|
| `Notes/` | 源稿 Markdown，按主题文件夹（最多三级） |
| `wiki/` | WIKI.md 索引、`{叶主题}_综述.md`、`log.md` |
| `Raw/` | 原件归档；自动转换扫描跳过此目录 |
| `.noteai/` | RAG、memory、日志、入库状态 |
| `.ai_memory/project_rules.md` | 本库主题细则（补充本 Schema） |

## 3. 主题

- 逻辑：`一级 > 二级 > 三级`；路径：`Notes/一级/二级/三级/标题.md`
- **文件夹是事实来源**；`WIKI.md` 必须与 `Notes/` 一致（应用内操作后重建同步）
- frontmatter `topic` 与文件夹冲突 → **以文件夹为准** 并回写
- 不确定 → `.pending_topics.json`，禁止扔进「其他/杂项/未分类」
- 优先复用已有主题名；新主题 2～8 字，中文

```yaml
---
topic: AI Agent > 记忆系统
tags: [Agent, 记忆, RAG]
title: 文章标题
---
```

- 标签 2～5 个，中文、有区分度；文件名=标题，禁用 `/ \\ : * ? \" < > |`

## 4. 入库

顺序：转换 → 分类 → RAG 索引 → 级联综述（仅触达主题）→ 同步 WIKI。`Raw/` 内文件不重复自动转换。

## 5. 级联与编译

- **只写** `wiki/*_综述.md` 与 WIKI；**只读** 同 topic 的 `Notes/` 笔记作素材，不改平行笔记正文
- 综述引用来源文件名；增量更新保留已有有效内容
- 链接发现默认待确认（`.links.json`）

## 6. AI 可写范围

```yaml
ai_may_edit_wiki: true
ai_may_edit_notes: false
max_topic_depth: 3
```

允许：综述、WIKI、wiki/log、frontmatter topic/tags、RAG 索引。禁止：改 Notes 正文、删笔记、四级主题、`<!-- human-lock -->` 段落。

## 7. 冲突

综述与笔记矛盾 → 综述并列记录并注明来源，不改 Notes。详见 `docs/schema.template.md`。
"""
