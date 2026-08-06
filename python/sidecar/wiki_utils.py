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
from utils.wiki_manager import (
    collect_survey_off_topics as _collect_survey_off_topics_impl,
)
from utils.wiki_manager import _get_wiki_path as _resolve_wiki_path_impl
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
    - stale: 主题下笔记最新修改晚于综述文件（仅 has_survey 时计算，轻量扫描）
    """
    if workspace_str is None:
        workspace_str = config.workspace_path or ""
    ws = Path(workspace_str)
    if not ws.exists():
        return {}

    enabled_map = get_survey_status(workspace_str)
    headings = _parse_wiki_headings_full()

    from sidecar.cascade import collect_topic_notes, get_survey_path

    overview: dict[str, dict] = {}
    for heading in headings:
        topic = heading["name"]
        survey_path = get_survey_path(topic)
        has_survey = bool(survey_path and survey_path.exists())
        stale = False
        if has_survey and survey_path is not None:
            try:
                survey_mtime = survey_path.stat().st_mtime
                note_mtimes = []
                for note in collect_topic_notes(topic, include_content=False):
                    note_path = ws / note["file_path"]
                    if note_path.exists():
                        note_mtimes.append(note_path.stat().st_mtime)
                stale = bool(note_mtimes) and max(note_mtimes) > survey_mtime
            except Exception:
                stale = False
        overview[topic] = {
            "enabled": enabled_map.get(topic, True),
            "has_survey": has_survey,
            "stale": stale,
            "survey_path": str(survey_path.relative_to(ws)) if has_survey and survey_path else "",
        }
    return overview
