#!/usr/bin/env python3
"""Apply i18n: generate en.json translations and patch JS to use window.t()."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "webui" / "locales"
JS_DIR = ROOT / "webui" / "js"
SKIP_JS = {"i18n.js"}


def flatten(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


def unflatten(flat: dict[str, str]) -> dict:
    root: dict = {}
    for key, val in flat.items():
        parts = key.split(".")
        cur = root
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = val
    return root


# English translations keyed by zh-CN text (value lookup)
EN_BY_ZH: dict[str, str] = {
    "取消": "Cancel",
    "确认": "Confirm",
    "关闭": "Close",
    "保存": "Save",
    "已保存": "Saved",
    "加载中...": "Loading…",
    "加载中…": "Loading…",
    "暂无工作区": "No workspace",
    "暂无数据": "No data",
    "设置": "Settings",
    "待处理": "Pending",
    "笔记": "Notes",
    "主题": "Topics",
    "标签": "Tags",
    "入库": "Ingest",
    "重试": "Retry",
    "发送": "Send",
    "搜索笔记...": "Search notes…",
    "下载": "Download",
    "网页": "Web",
    "转录": "Transcript",
    "开始下载": "Start download",
    "小忆助手": "XiaoYi Assistant",
    "问答模式": "Q&A mode",
    "助手模式": "Agent mode",
    "模型": "Model",
    "界面": "Appearance",
    "关于": "About",
    "操作记录": "Activity log",
    "云盘同步": "Cloud sync",
    "保存配置": "Save settings",
    "浅色": "Light",
    "深色": "Dark",
    "纸质": "Paper",
    "跟随系统": "System",
    "小": "Small",
    "中": "Medium",
    "大": "Large",
    "就绪": "Ready",
    "初始化完成": "Ready",
    "正在加载...": "Loading…",
    "健康检查": "Health check",
    "全部重试综述": "Retry all surveys",
    "没有待处理的事项": "Nothing pending",
    "选择文件以预览": "Select a file to preview",
    "展开侧边栏": "Expand sidebar",
    "收起侧边栏": "Collapse sidebar",
    "新建主题": "New topic",
    "新建笔记": "New note",
    "打开工作区": "Open workspace",
    "导入文件": "Import files",
    "网页下载": "Download from web",
    "目录树": "File tree",
    "双向链接": "Bidirectional links",
    "关系图谱": "Relation graph",
    "搜索 (Cmd+K)": "Search (Cmd+K)",
    "AI 助手": "AI assistant",
    "编辑": "Edit",
    "关闭预览": "Close preview",
    "确认创建标签": "Confirm create tag",
    "输入标签名称...": "Enter tag name…",
    "0 篇笔记": "0 notes",
    "0 个标签": "0 tags",
    "0 个链接": "0 links",
    "0 项": "0 items",
    "布局参数": "Layout settings",
    "恢复默认": "Reset defaults",
    "应用": "Apply",
    "放大": "Zoom in",
    "缩小": "Zoom out",
    "重放动画": "Replay animation",
    "刷新图谱": "Refresh graph",
    "关闭图谱": "Close graph",
    "全部": "All",
    "全部确认": "Confirm all",
    "待确认链接": "Links to confirm",
    "暂无待确认链接": "No links to confirm",
    "加粗": "Bold",
    "斜体": "Italic",
    "删除线": "Strikethrough",
    "行内代码": "Inline code",
    "标题 1": "Heading 1",
    "标题 2": "Heading 2",
    "标题 3": "Heading 3",
    "无序列表": "Bullet list",
    "有序列表": "Ordered list",
    "任务列表": "Task list",
    "引用": "Quote",
    "代码块": "Code block",
    "链接": "Link",
    "图片": "Image",
    "撤销": "Undo",
    "重做": "Redo",
    "快速新建": "Quick create",
    "创建并打开": "Create & open",
    "创建主题": "Create topic",
    "跳过": "Skip",
    "保存规则": "Save rules",
    "项目规则": "Project rules",
    "配置工作区 Schema": "Configure workspace schema",
    "上一步": "Back",
    "下一步": "Next",
    "完成并保存": "Finish & save",
    "使用推荐默认": "Use recommended defaults",
    "取消入库": "Cancel ingest",
    "重新入库": "Retry ingest",
    "入库完成": "Ingest complete",
    "入库已取消": "Ingest cancelled",
    "入库进行中…": "Ingest in progress…",
    "查看详情": "View details",
    "请先选择一个文件": "Please select a file first",
    "解析失败": "Parse failed",
    "保存失败": "Save failed",
    "保存中...": "Saving…",
    "搜索不可用": "Search unavailable",
    "搜索中...": "Searching…",
    "搜索失败": "Search failed",
    "未找到匹配": "No matches found",
    "开始转换": "Start conversion",
    "转换中...": "Converting…",
    "转换完成": "Conversion complete",
    "转换失败": "Conversion failed",
    "系统": "System",
    "小忆": "XiaoYi",
    "请求失败": "Request failed",
    "未知错误": "Unknown error",
    "所有事项已处理完毕 ✓": "All done ✓",
    "所有事项已处理完毕 🎉": "All done 🎉",
    "加载失败": "Load failed",
    "笔记整合": "Note integration",
    "提取主题": "Extract topics",
    "开始整合": "Start integration",
    "主题设置": "Topic settings",
    "收起": "Collapse",
    "一级": "L1",
    "二级": "L2",
    "三级": "L3",
    " 综述": " survey",
    "综述": "Survey",
    "Lint": "Lint",
    "语言": "Language",
    "中文": "中文",
    "English": "English",
}


def translate_zh_to_en(zh: str) -> str:
    if zh in EN_BY_ZH:
        return EN_BY_ZH[zh]
    if not re.search(r"[\u4e00-\u9fff]", zh):
        return zh
    # Pattern replacements for common UI phrases
    s = zh
    replacements = [
        (r"正在(.+?)\.\.\.", r"\1…"),
        (r"正在(.+?)…", r"\1…"),
        (r"(.+?)失败", r"\1 failed"),
        (r"(.+?)完成", r"\1 complete"),
        (r"(.+?)成功", r"\1 succeeded"),
        (r"暂无(.+)", r"No \1 yet"),
        (r"加载(.+?)失败", r"Failed to load \1"),
        (r"保存(.+?)失败", r"Failed to save \1"),
        (r"删除(.+?)失败", r"Failed to delete \1"),
        (r"创建(.+?)失败", r"Failed to create \1"),
        (r"请先(.+)", r"Please \1 first"),
        (r"确定要(.+?)吗？", r"Are you sure you want to \1?"),
        (r"(\d+) 篇笔记", r"{count} notes"),
        (r"(\d+) 个标签", r"{count} tags"),
        (r"(\d+) 个链接", r"{count} links"),
        (r"(\d+) 项", r"{count} items"),
    ]
    # Simple word map for partial translation
    word_map = {
        "笔记": "notes",
        "主题": "topic",
        "标签": "tags",
        "链接": "links",
        "文件": "files",
        "文件夹": "folder",
        "工作区": "workspace",
        "设置": "settings",
        "配置": "config",
        "保存": "save",
        "加载": "load",
        "删除": "delete",
        "创建": "create",
        "导入": "import",
        "下载": "download",
        "上传": "upload",
        "搜索": "search",
        "索引": "index",
        "综述": "survey",
        "入库": "ingest",
        "转换": "convert",
        "健康检查": "health check",
        "待处理": "pending",
        "助手": "assistant",
        "问答": "Q&A",
        "模式": "mode",
        "用户画像": "user profile",
        "操作记录": "activity log",
        "云盘": "cloud drive",
        "同步": "sync",
        "授权": "authorize",
        "推送": "push",
        "拉取": "pull",
        "断开": "disconnect",
        "已连接": "Connected",
        "未连接": "Not connected",
        "一级": "Level 1",
        "二级": "Level 2",
        "三级": "Level 3",
        "布局": "layout",
        "图谱": "graph",
        "预览": "preview",
        "编辑器": "editor",
        "元数据": "metadata",
        "标题": "title",
        "名称": "name",
        "取消": "cancel",
        "确认": "confirm",
        "关闭": "close",
        "重试": "retry",
        "全部": "all",
        "个": "",
        "篇": "",
        "项": "items",
    }
    # Fallback: transliterate key parts for graph layout (keep technical terms)
    if "px" in s or "alpha" in s or "rad" in s or "系数" in s or "斥力" in s:
        out = s
        for cn, en in word_map.items():
            out = out.replace(cn, en + " " if en else "")
        out = re.sub(r"\s+", " ", out).strip()
        return out if out else zh
    # Generic fallback with word substitution
    out = s
    for cn, en in sorted(word_map.items(), key=lambda x: -len(x[0])):
        if cn in out and en:
            out = out.replace(cn, en)
    out = re.sub(r"\s+", " ", out).strip()
    return out if out != s else f"[TODO] {zh}"


def generate_en(zh_data: dict) -> dict:
    flat = flatten(zh_data)
    en_flat = {k: translate_zh_to_en(v) for k, v in flat.items()}
    return unflatten(en_flat)


def _ui_line(line: str) -> bool:
    markers = (
        "innerHTML", "textContent", "placeholder", ".title", "showStatus",
        "updateStatus", "alert(", "confirm(", "prompt(", "ToastModule",
        "badge.textContent", "label.textContent", "btn.textContent",
        "setSidebarStatus", "aria-label", "document.title",
    )
    return any(m in line for m in markers)


def patch_js(flat: dict[str, str]) -> int:
    """Replace UI string literals with window.t('key') in JS files."""
    items = sorted(flat.items(), key=lambda x: -len(x[1]))
    total = 0
    for js_path in sorted(JS_DIR.glob("*.js")):
        if js_path.name in SKIP_JS:
            continue
        lines = js_path.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = False
        for li, line in enumerate(lines):
            if not _ui_line(line):
                continue
            new_line = line
            for key, text in items:
                if len(text) < 2 or "window.t(" in text:
                    continue
                repl = f"window.t('{key}')"
                for q in ("'", '"'):
                    old = f"{q}{text}{q}"
                    if old in new_line and repl not in new_line:
                        new_line = new_line.replace(old, repl)
                        total += 1
                if text in new_line and repl not in new_line:
                    new_line = new_line.replace(text, "' + " + repl + " + '")
                    total += 1
            if new_line != line:
                lines[li] = new_line
                changed = True
        if changed:
            js_path.write_text("".join(lines), encoding="utf-8")
            print(f"  patched {js_path.name}")
    return total


def main() -> None:
    zh_path = LOCALES / "zh-CN.json"
    zh_data = json.loads(zh_path.read_text(encoding="utf-8"))
    flat = flatten(zh_data)

    en_data = generate_en(zh_data)
    (LOCALES / "en.json").write_text(
        json.dumps(en_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Generated en.json ({len(flat)} keys)")

    print("Patching JS files...")
    n = patch_js(flat)
    print(f"Applied {n} replacements")


if __name__ == "__main__":
    main()
