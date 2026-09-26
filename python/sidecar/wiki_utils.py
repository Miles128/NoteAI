"""WIKI.md unified interface — single source of truth for all WIKI.md I/O.

All WIKI.md read/write operations MUST go through this module.
Downstream code should never open/read/write WIKI.md directly.

底层实现拆在 utils/wiki/{parse,crud,sync}.py；utils/wiki_store.py 为对外门面。
"""

from datetime import datetime
from pathlib import Path

from config.constants import TOPIC_SEP
from utils.atomic_write import atomic_write_text
from utils.wiki_store import (
    _get_wiki_path as _resolve_wiki_path_impl,
)
from utils.wiki_store import (
    _write_file_topic_from_folder as _write_file_topic_from_folder_impl,
)
from utils.wiki_store import (
    add_file_to_wiki_topic,  # noqa: F401  (facade re-export)
    create_topic,  # noqa: F401  (facade re-export)
    delete_topic,  # noqa: F401  (facade re-export)
    remove_file_from_wiki_topic,  # noqa: F401  (facade re-export)
    rename_topic,  # noqa: F401  (facade re-export)
)
from utils.wiki_store import (
    collect_survey_off_topics as _collect_survey_off_topics_impl,
)
from utils.wiki_store import (
    parse_wiki_headings as _parse_wiki_headings_full,
)
from utils.wiki_store import (
    parse_wiki_structure as _parse_wiki_structure_full,
)
from utils.wiki_store import (
    sync_wiki_with_files as _sync_wiki_with_files_impl,
)
from utils.wiki_store import (
    topic_from_notes_path as _topic_from_notes_path_impl,
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
    return _sync_wiki_with_files_impl()


def write_file_topic_from_folder(file_path: Path, topic: str | None) -> bool:
    return _write_file_topic_from_folder_impl(file_path, topic)


def topic_from_notes_path(file_path: str | Path) -> str | None:
    return _topic_from_notes_path_impl(file_path)


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
        atomic_write_text(wiki_path, content)
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
        atomic_write_text(wiki_path, "\n## ".join(rebuilt))
    except Exception as exc:
        return {"success": False, "message": f"写入 WIKI.md 失败：{exc}"}
    return {"success": True, "injected": injected}


def ensure_wiki_exists(workspace_str: str | Path | None = None) -> Path:
    wiki_path = resolve_wiki_path(workspace_str)
    if not wiki_path.exists():
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"
        atomic_write_text(wiki_path, content)
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


def collect_survey_off_topics(
    workspace_str: str | Path | None = None,
) -> set[str]:
    return _collect_survey_off_topics_impl(workspace_str)
