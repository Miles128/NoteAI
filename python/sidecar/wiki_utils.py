"""WIKI.md unified interface — single source of truth for all WIKI.md I/O.

All WIKI.md read/write operations MUST go through this module.
Downstream code should never open/read/write WIKI.md directly.

Lower-level helpers live in:
  - utils.wiki_manager: path resolution, heading parsing, renumbering, survey-off parsing
  - utils.wiki_crud: CRUD (add/remove/rename topics & files)
  - utils.wiki_sync: folder sync / topic inference
  - utils.topic_dedup: merge/dedup

Note: wiki_sync imports are deferred to function bodies because
utils.wiki_sync imports this module (collect_survey_off_topics).

The wiki_crud names imported above are public facade re-exports.
"""

from datetime import datetime
from pathlib import Path

from config import config
from config.constants import TOPIC_SEP
from utils.wiki_crud import (  # noqa: F401  (facade re-exports)
    add_file_to_wiki_topic,
    create_topic,
    delete_topic,
    remove_file_from_wiki_topic,
    rename_topic,
)
from utils.wiki_manager import _get_wiki_path as _resolve_wiki_path_impl
from utils.wiki_manager import (
    collect_survey_off_topics as _collect_survey_off_topics_impl,
)
from utils.wiki_manager import (
    parse_wiki_headings as _parse_wiki_headings_full,
)
from utils.wiki_manager import (
    parse_wiki_structure as _parse_wiki_structure_full,
)


def resolve_wiki_path(workspace_str: str | Path | None = None) -> Path:
    wiki_path = _resolve_wiki_path_impl(workspace_str)
    assert wiki_path is not None, "workspace not configured"
    return wiki_path


def parse_wiki_headings() -> list:
    return _parse_wiki_headings_full()


def parse_wiki_structure() -> list:
    return _parse_wiki_structure_full()


def sync_wiki_with_files():
    from utils.wiki_sync import sync_wiki_with_files as _impl

    return _impl()


def write_file_topic_from_folder(file_path: Path, topic: str | None) -> bool:
    from utils.wiki_sync import _write_file_topic_from_folder as _impl

    return _impl(file_path, topic)


def topic_from_notes_path(file_path: str | Path) -> str | None:
    from utils.wiki_sync import topic_from_notes_path as _impl

    return _impl(file_path)


def read_wiki_text(workspace_str: str | Path | None = None) -> str | None:
    wiki_path = resolve_wiki_path(workspace_str)
    if not wiki_path.exists():
        return None
    try:
        return wiki_path.read_text(encoding="utf-8")
    except Exception:
        return None


def write_wiki_text(content: str, workspace_str: str | Path | None = None) -> bool:
    wiki_path = resolve_wiki_path(workspace_str)
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        wiki_path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


_SEMANTIC_LINK_MARKER = "<!-- NOTEAI_SEMANTIC_LINK -->"


def _semantic_card_link(top: str, semantic_dir: Path) -> str | None:
    """Return the markdown link line for a top-level semantic card, if present."""
    if not top or top in {"目录", "标签索引"} or "/" in top:
        return None
    card = semantic_dir / f"{top}_语义.md"
    if not card.is_file():
        return None
    return f"- **语义知识卡**：[{top} · 语义知识](semantic/{top}_语义.md) {_SEMANTIC_LINK_MARKER}"


def sync_semantic_links(workspace_str: str | Path | None = None) -> dict:
    """Inject semantic knowledge-card links into each WIKI.md top-level section.

    Idempotent: sections already carrying the NOTEAI_SEMANTIC_LINK marker are
    skipped; only sections whose `semantic/{top}_语义.md` exists get a link.
    Best-effort: returns a dict, never raises.
    """
    wiki_path = resolve_wiki_path(workspace_str)
    if not wiki_path.exists():
        return {"success": False, "message": "WIKI.md 不存在"}
    semantic_dir = wiki_path.parent / "semantic"
    if not semantic_dir.is_dir():
        return {"success": False, "message": "语义知识目录不存在"}
    try:
        text = wiki_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"success": False, "message": f"读取 WIKI.md 失败：{exc}"}
    parts = text.split("\n## ")
    head, blocks = parts[0], parts[1:]
    rebuilt = [head]
    injected = 0
    for block in blocks:
        first_line, sep, body = block.partition("\n")
        if _SEMANTIC_LINK_MARKER not in block:
            link = _semantic_card_link(first_line.strip(), semantic_dir)
            if link is not None:
                body = body.rstrip("\n") + "\n" + link + "\n"
                injected += 1
        rebuilt.append(first_line + sep + body)
    try:
        wiki_path.write_text("\n## ".join(rebuilt), encoding="utf-8")
    except Exception as exc:
        return {"success": False, "message": f"写入 WIKI.md 失败：{exc}"}
    return {"success": True, "injected": injected}


def ensure_wiki_exists(workspace_str: str | Path | None = None) -> Path:
    wiki_path = resolve_wiki_path(workspace_str)
    if not wiki_path.exists():
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"
        wiki_path.write_text(content, encoding="utf-8")
    return wiki_path


def get_all_topic_names(workspace_str: str | Path | None = None) -> list[str]:
    headings = _parse_wiki_headings_full()
    return [h["name"] for h in headings]


def get_survey_status(workspace_str: str | Path | None = None) -> dict[str, bool]:
    text = read_wiki_text(workspace_str)
    if text is None:
        return {}
    lines = text.split("\n")
    surveys: dict[str, bool] = {}
    current_parent = ""
    for i in range(len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("## "):
            current_parent = stripped[3:].strip()
            is_off = i + 1 < len(lines) and lines[i + 1].strip() == "> 综述: off"
            surveys[current_parent] = not is_off
        elif stripped.startswith("### ") and current_parent:
            child = stripped[4:].strip()
            full = f"{current_parent}{TOPIC_SEP}{child}"
            parent_on = surveys.get(current_parent, True)
            if parent_on:
                surveys[full] = False
            else:
                is_off = i + 1 < len(lines) and lines[i + 1].strip() == "> 综述: off"
                surveys[full] = not is_off
    return surveys


def toggle_survey(
    topic_name: str,
    workspace_str: str | Path | None = None,
) -> dict:
    wiki_path = resolve_wiki_path(workspace_str)
    if not wiki_path.exists():
        return {"success": False, "message": "WIKI.md 不存在"}

    try:
        text = wiki_path.read_text(encoding="utf-8")
    except Exception:
        return {"success": False, "message": "读取 WIKI.md 失败"}

    lines = text.split("\n")
    new_lines: list[str] = []
    current_parent = ""
    is_parent = TOPIC_SEP not in topic_name
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()
        new_lines.append(lines[i])

        if stripped.startswith("## "):
            current_parent = stripped[3:].strip()

            if is_parent and current_parent == topic_name:
                if i + 1 < len(lines) and lines[i + 1].strip() == "> 综述: off":
                    i += 1
                else:
                    new_lines.append("> 综述: off")
                    i += 1
                i += 1
                while i < len(lines):
                    s = lines[i].strip()
                    if s.startswith("## "):
                        new_lines.append(lines[i])
                        i += 1
                        break
                    if s.startswith("### ") and current_parent:
                        child = s[4:].strip()
                        full = f"{current_parent}{TOPIC_SEP}{child}"
                        new_lines.append(lines[i])
                        i += 1
                        if i < len(lines) and lines[i].strip() == "> 综述: off":
                            i += 1
                        while i < len(lines):
                            ns = lines[i].strip()
                            if ns.startswith("## ") or ns.startswith("### "):
                                break
                            new_lines.append(lines[i])
                            i += 1
                    else:
                        new_lines.append(lines[i])
                        i += 1
                        if s.startswith("## "):
                            break
                continue
        elif stripped.startswith("### ") and current_parent and not is_parent:
            child = stripped[4:].strip()
            full = f"{current_parent}{TOPIC_SEP}{child}"
            if full == topic_name:
                if i + 1 < len(lines) and lines[i + 1].strip() == "> 综述: off":
                    i += 1
                else:
                    new_lines.append("> 综述: off")
                    i += 1
                i += 1
                continue

        i += 1

    wiki_path.write_text("\n".join(new_lines), encoding="utf-8")
    return {"success": True, "message": "已切换综述状态"}


def collect_survey_off_topics(
    workspace_str: str | Path | None = None,
) -> set[str]:
    return _collect_survey_off_topics_impl(workspace_str)


def get_survey_overview(workspace_str: str | Path | None = None) -> dict[str, dict]:
    """主题综述状态总览：{topic: {enabled, has_survey, stale, survey_path}}

    - enabled: WIKI.md 综述开关（默认开）
    - has_survey: wiki/{末级}_综述.md 是否存在
    - stale: 主题下笔记最新修改晚于综述文件（仅 has_survey 时计算）

    单次全库遍历：一次 rglob + 逐文件头部 frontmatter 解析，按候选主题
    聚合最新 mtime（原实现逐主题调用 collect_topic_notes → O(主题数×文件数)）。
    """
    if workspace_str is None:
        workspace_str = config.workspace_path or ""
    ws = Path(workspace_str)
    if not ws.exists():
        return {}

    enabled_map = get_survey_status(workspace_str)
    headings = _parse_wiki_headings_full()

    overview: dict[str, dict] = {}
    if not headings:
        return overview

    from config.settings import NOTES_FOLDER
    from sidecar.cascade import get_survey_path
    from utils.text_utils import parse_frontmatter

    # 候选主题分组：topic_parts（'a::b' 前缀匹配用）
    candidate_parts: dict[str, list[str]] = {}
    for heading in headings:
        topic = heading["name"]
        parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
        candidate_parts[topic] = parts
        overview[topic] = {
            "enabled": enabled_map.get(topic, True),
            "has_survey": False,
            "stale": False,
            "survey_path": "",
        }

    # 单次遍历聚合每主题最新笔记 mtime（判定与 cascade.collect_topic_notes 一致：
    # frontmatter topic/topics + Notes 目录路径前缀）
    notes_dir = ws / NOTES_FOLDER
    notes_dir_exists = notes_dir.exists()
    latest_mtime: dict[str, float] = {}
    for md_file in ws.rglob("*.md"):
        if md_file.name.startswith("."):
            continue
        if "wiki" in md_file.parts:
            continue
        if md_file.name.endswith("_综述.md") or md_file.name.endswith("综述.md"):
            continue
        try:
            with md_file.open("r", encoding="utf-8") as fh:
                text = fh.read(8192)
            fm, _body = parse_frontmatter(text)
        except Exception:
            continue
        file_topic = ""
        file_topics: list = []
        if fm:
            ft = fm.get("topic", "")
            if isinstance(ft, str):
                file_topic = ft.strip() or ""
            fts = fm.get("topics", [])
            if isinstance(fts, list):
                file_topics = fts
        rel_parts: tuple = ()
        if notes_dir_exists:
            try:
                rel_parts = md_file.relative_to(notes_dir).parts
            except ValueError:
                rel_parts = ()
        try:
            mtime = md_file.stat().st_mtime
        except OSError:
            continue

        for topic, parts in candidate_parts.items():
            if not parts:
                continue
            matched = bool(
                file_topic
                and (
                    file_topic == topic
                    or file_topic.startswith(topic + TOPIC_SEP)
                    or len(parts) == 1
                    and (file_topic == parts[0] or file_topic.startswith(parts[0] + TOPIC_SEP))
                )
            )
            if not matched and topic in file_topics:
                matched = True
            if not matched and rel_parts and rel_parts[0] == parts[0]:
                if len(parts) == 1:
                    matched = True
                elif len(rel_parts) >= 2 and rel_parts[1] == parts[1]:
                    if len(parts) == 2 or len(rel_parts) >= 3 and rel_parts[2] == parts[2]:
                        matched = True
            if matched and mtime > latest_mtime.get(topic, float("-inf")):
                latest_mtime[topic] = mtime

    # 计算 stale 并补齐 survey_path
    for topic, entry in overview.items():
        survey_path = get_survey_path(topic)
        has_survey = bool(survey_path and survey_path.exists())
        entry["has_survey"] = has_survey
        if has_survey and survey_path is not None:
            try:
                stale = latest_mtime.get(topic, 0.0) > survey_path.stat().st_mtime
            except Exception:
                stale = False
            entry["stale"] = stale
            entry["survey_path"] = str(survey_path.relative_to(ws))
    return overview
