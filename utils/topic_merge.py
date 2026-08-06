"""LLM-assisted naming and safe migration for similar topic pairs.

主题合并（文件/frontmatter 侧）在 utils/ 的唯一入口；WIKI 段侧的合并去重
见 utils.topic_dedup。前端 RPC 经 handlers/topics_handler.py 调用本模块的
suggest_merged_topic_names / preview_topic_merge / merge_topics。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from config.constants import TOPIC_SEP
from config.settings import ABSTRACT_FOLDER, NOTES_FOLDER, WORKSPACE_APP_FOLDER
from utils.text_utils import parse_frontmatter


def _topic_dir(root: Path, topic: str) -> Path:
    parts = [part.strip() for part in topic.split(TOPIC_SEP) if part.strip()]
    if not parts or len(parts) > 3 or any(part in {".", ".."} or "/" in part or "\\" in part for part in parts):
        raise ValueError("主题名称非法")
    return root / NOTES_FOLDER / Path(*parts)


def _survey_excerpts(root: Path, topics: list[str]) -> list[str]:
    """Read up to one survey per topic from the wiki for naming context (PRD §9.4)."""
    wiki = root / ABSTRACT_FOLDER
    excerpts: list[str] = []
    for topic in topics:
        leaf = topic.rsplit(TOPIC_SEP, maxsplit=1)[-1]
        survey_paths: list[Path] = []
        flat = wiki / f"{leaf}_综述.md"
        if flat.exists():
            survey_paths.append(flat)
        parts = [part.strip() for part in topic.split(TOPIC_SEP) if part.strip()]
        if parts and all(part not in {".", ".."} and "/" not in part and "\\" not in part for part in parts):
            topic_dir = wiki.joinpath(*parts)
            if topic_dir.is_dir():
                survey_paths.extend(sorted(topic_dir.rglob("*_综述.md"))[:1])
        for survey in survey_paths[:1]:
            try:
                _, body = parse_frontmatter(survey.read_text(encoding="utf-8"))
            except OSError:
                continue
            if body.strip():
                excerpts.append(f"主题综述「{topic}」：\n{body.strip()[:800]}")
    return excerpts


def _representative_chunks(root: Path, topics: list[str]) -> list[str]:
    """Pick up to two stored chunks per topic from the similarity graph for naming context."""
    graph_path = root / WORKSPACE_APP_FOLDER / "chunk_similarity_graph.json"
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    by_topic: dict[str, list[str]] = {}
    for chunk in graph.get("chunks") or []:
        topic = str(chunk.get("topic") or "").strip()
        content = str(chunk.get("content") or "").strip()
        if topic in topics and content:
            by_topic.setdefault(topic, []).append(content)
    excerpts: list[str] = []
    for topic in topics:
        for content in by_topic.get(topic, [])[:2]:
            excerpts.append(f"主题「{topic}」代表性片段：\n{content[:300]}")
    return excerpts


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
    samples.extend(_survey_excerpts(root, topics))
    samples.extend(_representative_chunks(root, topics))
    prompt = """请为两个准备合并的知识主题提出 3 个简洁、准确、互不重复的新中文主题名。
参考以下笔记片段、主题综述与代表性片段；新主题名应同时覆盖两边的核心内容。
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


def preview_topic_merge(workspace: str | Path, topics: list[str], new_topic: str) -> dict:
    """Preview a topic merge: migrated notes, same-name conflicts and affected surveys (PRD §9.4)."""
    if len(topics) != 2 or topics[0] == topics[1]:
        return {"success": False, "message": "请选择两个不同主题"}
    root = Path(workspace).resolve()
    target = _topic_dir(root, new_topic)
    sources = [_topic_dir(root, topic) for topic in topics]
    if not all(source.is_dir() for source in sources):
        return {"success": False, "message": "源主题目录不存在"}
    notes = sorted(note for source in sources for note in source.rglob("*.md"))
    target_names = {path.name for path in target.rglob("*.md")} if target.is_dir() else set()
    conflicts = []
    for note in notes:
        if note.name in target_names:
            conflicts.append(
                {
                    "name": note.name,
                    "source": str(note.relative_to(root)),
                    "target": str((target / note.name).relative_to(root)),
                }
            )
    wiki = root / ABSTRACT_FOLDER
    surveys: list[str] = []
    for topic in topics:
        leaf = topic.rsplit(TOPIC_SEP, maxsplit=1)[-1]
        flat = wiki / f"{leaf}_综述.md"
        if flat.exists():
            surveys.append(str(flat.relative_to(root)))
        parts = [part.strip() for part in topic.split(TOPIC_SEP) if part.strip()]
        if parts and all(part not in {".", ".."} and "/" not in part and "\\" not in part for part in parts):
            topic_dir = wiki.joinpath(*parts)
            if topic_dir.is_dir():
                for survey in sorted(topic_dir.rglob("*_综述.md")):
                    surveys.append(str(survey.relative_to(root)))
    return {
        "success": True,
        "note_count": len(notes),
        "notes": [str(note.relative_to(root)) for note in notes],
        "conflicts": conflicts,
        "surveys": sorted(set(surveys)),
    }


def merge_topics(workspace: str | Path, topics: list[str], new_topic: str) -> dict:
    if len(topics) != 2 or topics[0] == topics[1]:
        return {"success": False, "message": "请选择两个不同主题"}
    root = Path(workspace).resolve()
    target = _topic_dir(root, new_topic)
    sources = [_topic_dir(root, topic) for topic in topics]
    if not all(source.is_dir() for source in sources):
        return {"success": False, "message": "源主题目录不存在"}
    target.mkdir(parents=True, exist_ok=True)
    from utils.topic_file_ops import move_file_to_notes_topic_folder, write_topic_to_file

    moved: list[str] = []
    renamed: list[dict] = []
    for source in sources:
        for note in sorted(source.rglob("*.md")):
            write_result = write_topic_to_file(str(note), new_topic)
            if not write_result.get("success"):
                return {"success": False, "message": write_result.get("message", "主题写入失败"), "moved": moved}
            move_result = move_file_to_notes_topic_folder(str(note), new_topic)
            if not move_result.get("success"):
                return {"success": False, "message": move_result.get("message", "文件迁移失败"), "moved": moved}
            new_path = str(move_result.get("new_path") or "")
            moved.append(new_path)
            if Path(new_path).name != note.name:
                renamed.append({"from": note.name, "to": Path(new_path).name})
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
    rename_message = ""
    if renamed:
        rename_message = f"；{len(renamed)} 个同名文件已自动改名，未覆盖任何笔记"
    return {
        "success": True,
        "new_topic": new_topic,
        "moved": moved,
        "renamed": renamed,
        "message": f"已合并为主题「{new_topic}」" + rename_message,
    }
