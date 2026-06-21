"""Vault AGENTS.md 生成器。

为当前工作区生成 AGENTS.md 文件，描述 vault 结构、主题体系、笔记规范，
供 Claude Code / OpenCode / Codex 等 CLI agent 读取理解。

对标 Tolaria 的 AGENTS.md for Vault 设计。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import config
from config.constants import NOTES_FOLDER
from utils.logger import logger

VAULT_AGENTS_MD_TEMPLATE = """# AGENTS.md — NoteAI Vault Guide

> 本文件由 NoteAI 自动生成，供 Claude Code / OpenCode / Codex / Gemini 等 CLI agent 读取。
> 描述当前工作区的结构、主题体系和笔记规范。

## 工作区信息

- **工作区路径**: `{workspace_path}`
- **笔记目录**: `{notes_folder}/`
- **知识库目录**: `wiki/`（AI 生成的综述和索引）
- **原始文件归档**: `Raw/`（PDF/DOCX/PPTX 等非 Markdown 文件）

## 三层知识架构

```
Notes/        ← 原始笔记（Markdown，不可变来源）
wiki/         ← AI 编译的结构化知识（综述、WIKI.md 索引）
Raw/          ← 原始文件归档（PDF、DOCX、PPTX、图片等）
```

## 主题体系

NoteAI 使用三级主题分类：

- **一级主题** > **二级主题** > **三级主题**
- 文件系统结构: `Notes/一级/二级/三级/文件名.md`
- frontmatter 格式: `topic: 一级 > 二级 > 三级`
- 分隔符: ` > `
- 最多三层，三级下不再设子题

## 笔记规范

### 文件命名
- 文件名 = 文章标题
- 中文命名优先
- 避免特殊字符: `/ \\ : * ? " < > |`

### Frontmatter 字段
每篇笔记的 YAML frontmatter 可包含：
- `topic`: 主题路径（如 `人工智能 > 机器学习 > 深度学习`）
- `tags`: 标签列表
- `date`: 创建/采集日期
- `source`: 来源 URL（如有）
- `status`: 状态（可选）

### 综述文件
- 命名规范: `{{主题名}}_综述.md`
- 存放位置: `wiki/` 目录下按主题组织
- `WIKI.md` 仅含主题标题 + 文件列表

## AI 功能行为准则

1. **自动分类**: 以 `wiki/GUIDE.md` 中定义的主题归类规则为准
2. **标签提取**: 从标题和正文提取有区分度的关键词
3. **综述生成**: 针对二级主题，综合该主题下所有笔记内容
4. **知识问答**: 优先从知识库检索，结合工作区的主题体系给出回答
5. **级联更新**: 新资料入库时，主动检查并更新受影响的已有综述

## 两层记忆体系

- **L1 用户画像**: `<工作区>/.ai_memory/user_profile.json`
- **L2 工作区 Memory**: `<工作区>/.noteai/memory/`（RAG 会话记忆）

## Agent 操作建议

当作为 CLI agent 操作此 vault 时：

1. **读取笔记**: 使用 `cat` 或文件读取工具查看 `Notes/` 下的 Markdown 文件
2. **创建笔记**: 在对应的主题文件夹下创建 `.md` 文件，文件名 = 标题
3. **修改笔记**: 直接编辑 Markdown 文件，保留 frontmatter
4. **搜索笔记**: 使用 `grep -r "关键词" Notes/` 或类似工具
5. **生成综述**: 在 `wiki/` 目录下创建 `{{主题名}}_综述.md`
6. **更新 WIKI.md**: 在 `wiki/WIKI.md` 中添加主题和文件条目

## 当前工作区统计

- 笔记总数: {note_count}
- 主题总数: {topic_count}
- 综述总数: {survey_count}

---

*此文件由 NoteAI 于 {generated_at} 自动生成。如需更新，请在 NoteAI 中重新生成。*
"""


def _count_notes(notes_path: Path) -> int:
    """统计 Notes 目录下的 Markdown 文件数。"""
    if not notes_path.exists():
        return 0
    try:
        return sum(1 for _ in notes_path.rglob("*.md"))
    except Exception:
        return 0


def _count_topics(notes_path: Path) -> int:
    """统计主题文件夹数（一级 + 二级 + 三级）。"""
    if not notes_path.exists():
        return 0
    try:
        count = 0
        for item in notes_path.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                count += 1
                for sub in item.iterdir():
                    if sub.is_dir() and not sub.name.startswith("."):
                        count += 1
                        for subsub in sub.iterdir():
                            if subsub.is_dir() and not subsub.name.startswith("."):
                                count += 1
        return count
    except Exception:
        return 0


def _count_surveys(wiki_path: Path) -> int:
    """统计综述文件数。"""
    if not wiki_path.exists():
        return 0
    try:
        return sum(1 for f in wiki_path.rglob("*.md") if "综述" in f.name or "survey" in f.name.lower())
    except Exception:
        return 0


def generate_vault_agents_md() -> dict[str, Any]:
    """为当前工作区生成 AGENTS.md 文件。

    Returns:
        dict with success, message, path
    """
    ws = config.workspace_path
    if not ws:
        return {"success": False, "message": "未设置工作区"}

    ws_path = Path(ws).expanduser()
    if not ws_path.exists():
        return {"success": False, "message": f"工作区路径不存在: {ws}"}

    notes_path = ws_path / NOTES_FOLDER
    wiki_path = ws_path / "wiki"

    note_count = _count_notes(notes_path)
    topic_count = _count_topics(notes_path)
    survey_count = _count_surveys(wiki_path)

    from datetime import datetime
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = VAULT_AGENTS_MD_TEMPLATE.format(
        workspace_path=str(ws_path),
        notes_folder=NOTES_FOLDER,
        note_count=note_count,
        topic_count=topic_count,
        survey_count=survey_count,
        generated_at=generated_at,
    )

    agents_md_path = ws_path / "AGENTS.md"
    try:
        agents_md_path.write_text(content, encoding="utf-8")
        logger.info(f"[Vault AGENTS.md] 生成成功: {agents_md_path}")
        return {
            "success": True,
            "message": "AGENTS.md 已生成",
            "path": str(agents_md_path),
            "note_count": note_count,
            "topic_count": topic_count,
            "survey_count": survey_count,
        }
    except Exception as e:
        logger.exception("[Vault AGENTS.md] 生成失败")
        return {"success": False, "message": f"生成失败: {e}"}
