"""LLM-assisted naming and safe migration for similar topic pairs."""

from __future__ import annotations

import json
import re
from pathlib import Path

from config.constants import TOPIC_SEP
from config.settings import NOTES_FOLDER, WORKSPACE_APP_FOLDER
from utils.text_utils import parse_frontmatter


def _topic_dir(root: Path, topic: str) -> Path:
    parts = [part.strip() for part in topic.split(TOPIC_SEP) if part.strip()]
    if not parts or len(parts) > 3 or any(part in {".", ".."} or "/" in part or "\\" in part for part in parts):
        raise ValueError("主题名称非法")
    return root / NOTES_FOLDER / Path(*parts)


def suggest_merged_topic_names(workspace: str | Path, topics: list[str]) -> dict:
    if len(topics) != 2 or topics[0] == topics[1]:
        return {"success": False, "message": "请选择两个不同主题"}
    root = Path(workspace).resolve()
    samples: list[str] = []
    for topic in topics:
        folder = _topic_dir(root, topic)
        excerpts: list[str] = []
        for note in sorted(folder.rglob("*.md"))[:4]:
            _, body = parse_frontmatter(note.read_text(encoding="utf-8"))
            excerpts.append(f"{note.stem}: {body[:500]}")
        samples.append(f"主题：{topic}\n" + "\n".join(excerpts))
    prompt = """请为两个准备合并的知识主题提出 3 个简洁、准确、互不重复的新中文主题名。
返回严格 JSON：{"names":[{"name":"名称","reason":"理由"}]}。不要输出其他内容。

""" + "\n\n".join(samples)
    from utils.llm_utils import call_llm_raw

    raw = call_llm_raw(prompt, temperature=0.25).strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    try:
        data = json.loads(match.group(0) if match else raw)
        names = data.get("names") if isinstance(data, dict) else []
    except json.JSONDecodeError:
        names = []
    cleaned = [
        {"name": str(item.get("name") or "").strip(), "reason": str(item.get("reason") or "").strip()}
        for item in (names or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ][:3]
    return {"success": bool(cleaned), "names": cleaned, "message": "未生成有效主题名" if not cleaned else ""}


def merge_topics(workspace: str | Path, topics: list[str], new_topic: str) -> dict:
    if len(topics) != 2 or topics[0] == topics[1]:
        return {"success": False, "message": "请选择两个不同主题"}
    root = Path(workspace).resolve()
    target = _topic_dir(root, new_topic)
    sources = [_topic_dir(root, topic) for topic in topics]
    if not all(source.is_dir() for source in sources):
        return {"success": False, "message": "源主题目录不存在"}
    target.mkdir(parents=True, exist_ok=True)
    from utils.topic_assigner import move_file_to_notes_topic_folder, write_topic_to_file

    moved: list[str] = []
    for source in sources:
        for note in sorted(source.rglob("*.md")):
            write_result = write_topic_to_file(str(note), new_topic)
            if not write_result.get("success"):
                return {"success": False, "message": write_result.get("message", "主题写入失败"), "moved": moved}
            move_result = move_file_to_notes_topic_folder(str(note), new_topic)
            if not move_result.get("success"):
                return {"success": False, "message": move_result.get("message", "文件迁移失败"), "moved": moved}
            moved.append(str(move_result.get("new_path") or ""))
    for source in sorted(sources, key=lambda path: len(path.parts), reverse=True):
        current = source
        notes_root = root / NOTES_FOLDER
        while current != notes_root and current.is_dir():
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    alias_path = root / WORKSPACE_APP_FOLDER / "topic_aliases.json"
    try:
        aliases = json.loads(alias_path.read_text(encoding="utf-8"))
        if not isinstance(aliases, dict):
            aliases = {}
    except (OSError, json.JSONDecodeError):
        aliases = {}
    for topic in topics:
        aliases[topic] = new_topic
    alias_path.parent.mkdir(parents=True, exist_ok=True)
    temp = alias_path.with_suffix(".tmp")
    temp.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(alias_path)
    from sidecar.wiki_utils import sync_wiki_with_files

    sync_wiki_with_files()
    return {"success": True, "new_topic": new_topic, "moved": moved, "message": f"已合并为主题「{new_topic}」"}
