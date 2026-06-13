#!/usr/bin/env python3
"""Add data-i18n attributes to index.html static UI strings."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "webui" / "index.html"
LOCALES = ROOT / "webui" / "locales"

# title="..." -> data-i18n-title
TITLE_MAP: dict[str, str] = {
    "网页下载": "titlebar.webDownload",
    "导入文件": "titlebar.importFiles",
    "打开工作区": "titlebar.openWorkspace",
    "目录树": "titlebar.tree",
    "标签": "titlebar.tags",
    "双向链接": "titlebar.links",
    "关闭预览": "titlebar.closePreview",
    "待处理": "titlebar.pending",
    "AI 助手": "titlebar.aiAssistant",
    "编辑": "titlebar.edit",
    "关系图谱": "titlebar.graph",
    "搜索 (Cmd+K)": "titlebar.search",
    "设置": "titlebar.settings",
    "展开侧边栏": "titlebar.expandSidebar",
    "取消": "common.cancel",
    "确认创建标签": "sidebar.confirmCreateTag",
    "收起侧边栏": "sidebar.collapseSidebar",
    "新建主题": "sidebar.newTopic",
    "新建笔记": "sidebar.newNote",
    "自动匹配标签：扫描文件标题匹配已有标签": "sidebar.autoTagHint",
    "新加标签：创建新的标签分类": "sidebar.addTagHint",
    "发现链接：AI 分析文章关联": "sidebar.discoverLinksHint",
    "重新扫描断链、孤儿页、过时综述": "pending.healthCheckHint",
    "重试所有综述更新失败项": "pending.retryAllSurveysHint",
    "显示/隐藏文件名": "graph.toggleFilenames",
    "放大": "graph.zoomIn",
    "缩小": "graph.zoomOut",
    "重放动画": "graph.replay",
    "刷新图谱": "graph.refresh",
    "布局参数": "graph.layoutSettings",
    "关闭图谱": "graph.close",
    "收起": "common.collapse",
    "关闭": "common.close",
    "一键确认所有待确认链接": "links.confirmAll",
    "加粗": "editor.bold",
    "斜体": "editor.italic",
    "删除线": "editor.strike",
    "行内代码": "editor.inlineCode",
    "标题 1": "editor.heading1",
    "标题 2": "editor.heading2",
    "标题 3": "editor.heading3",
    "无序列表": "editor.bulletList",
    "有序列表": "editor.orderedList",
    "任务列表": "editor.taskList",
    "引用": "editor.blockquote",
    "代码块": "editor.codeBlock",
    "链接": "editor.link",
    "图片": "editor.image",
    "撤销": "editor.undo",
    "重做": "editor.redo",
    "LLM 改写：用中立客观风格重写文档": "editor.llmRewrite",
    "在设置 → 小忆助手中切换": "assistant.modeBadgeHint",
    "发送": "assistant.send",
    "提取主题：从网页内容中提取关键主题": "integrator.extractTopicsHint",
    "开始整合：将内容整合到笔记中": "integrator.startHint",
    "重新入库": "ingest.retry",
    "取消入库": "ingest.cancel",
}


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip())[:40]
    return s.strip("_") or "text"


def main() -> None:
    html = HTML.read_text(encoding="utf-8")
    zh: dict = {}

    def set_key(key: str, zh_text: str, en_text: str | None = None) -> None:
        parts = key.split(".")
        cur = zh
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = zh_text

    # titles
    for title, key in TITLE_MAP.items():
        html = html.replace(f'title="{title}"', f'data-i18n-title="{key}"')
        set_key(key, title)

    HTML.write_text(html, encoding="utf-8")
    print(f"Patched titles in {HTML}")


if __name__ == "__main__":
    main()
