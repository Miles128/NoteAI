from datetime import datetime
from pathlib import Path

import yaml
from sidecar.textutils import parse_frontmatter
from sidecar.wiki_utils import collect_survey_off_topics

from config import config
from config.constants import TOPIC_SEP
from utils.logger import logger
from utils.wiki_manager import _get_wiki_path


def _write_file_topic_from_folder(file_path: Path, topic: str | None) -> bool:
    try:
        text = file_path.read_text(encoding="utf-8")
        had_bom = text.startswith("\ufeff")

        raw_meta, body = parse_frontmatter(text)
        had_frontmatter = raw_meta is not None
        meta = raw_meta if isinstance(raw_meta, dict) else {}

        before = meta.get("topic")
        if topic:
            meta["topic"] = topic
        else:
            meta.pop("topic", None)

        if before == meta.get("topic") and had_frontmatter:
            return False

        prefix = "\ufeff" if had_bom else ""
        if meta:
            fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
            new_text = prefix + "---\n" + fm + "\n---\n" + body.lstrip("\n")
        else:
            new_text = prefix + body.lstrip("\n")
        file_path.write_text(new_text, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"[wiki_sync] update file topic failed {file_path}: {e}")
        return False


def _is_hidden_path(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def topic_from_notes_path(file_path: str | Path) -> str | None:
    workspace = config.workspace_path
    if not workspace:
        return None
    path = Path(file_path)
    notes_root = Path(workspace) / config.NOTES_FOLDER
    try:
        rel = path.relative_to(notes_root)
    except ValueError:
        return None
    if path.suffix.lower() != ".md":
        return None
    parts = rel.parts
    if len(parts) < 2:
        return None
    dir_parts = parts[:-1]
    if not dir_parts:
        return None
    if len(dir_parts) > 3:
        dir_parts = dir_parts[:3]
    return TOPIC_SEP.join(dir_parts)


def _topic_one_line_summary(topic: str, workspace_path: Path) -> str:
    leaf = topic.rsplit(TOPIC_SEP, maxsplit=1)[-1]
    survey = workspace_path / config.ABSTRACT_FOLDER / f"{leaf}_综述.md"
    if survey.exists():
        try:
            _, body = parse_frontmatter(survey.read_text(encoding="utf-8"))
            for line in body.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                text = stripped.lstrip(">-* ").strip()
                if text:
                    return text[:120]
        except OSError:
            pass

    notes_root = workspace_path / config.NOTES_FOLDER
    safe = topic.replace(TOPIC_SEP, "/")
    topic_dir = notes_root / safe
    if topic_dir.is_dir():
        for md in sorted(topic_dir.glob("*.md")):
            try:
                _, body = parse_frontmatter(md.read_text(encoding="utf-8"))
                for line in body.splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        return stripped[:120]
            except OSError:
                continue
    return ""


def sync_wiki_with_files():  # noqa: PLR0912, PLR0915
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "topics": 0, "files": 0, "updated": 0}

    workspace_path = Path(workspace)
    notes_root = workspace_path / config.NOTES_FOLDER
    wiki_path = _get_wiki_path()
    if not wiki_path:
        return {"success": False, "message": "WIKI.md 路径无效", "topics": 0, "files": 0, "updated": 0}

    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    off_topics = collect_survey_off_topics()

    topic_files: dict[str, list[str]] = {}
    topic_parts: dict[str, tuple[str, ...]] = {}
    root_md_files: list[Path] = []
    updated_files = 0

    if notes_root.exists():
        for directory in sorted(
            (p for p in notes_root.rglob("*") if p.is_dir()), key=lambda p: str(p.relative_to(notes_root))
        ):
            try:
                rel_parts = directory.relative_to(notes_root).parts
            except ValueError:
                continue
            if not rel_parts or _is_hidden_path(Path(*rel_parts)):
                continue
            for depth in range(1, min(len(rel_parts), 3) + 1):
                parts = tuple(rel_parts[:depth])
                topic = TOPIC_SEP.join(parts)
                topic_parts.setdefault(topic, parts)
                topic_files.setdefault(topic, [])

        for md_file in sorted(notes_root.rglob("*.md"), key=lambda p: str(p.relative_to(notes_root))):
            try:
                rel_parts = md_file.relative_to(notes_root).parts
            except ValueError:
                continue
            if _is_hidden_path(Path(*rel_parts)) or md_file.name in ("WIKI.md", "tags.md"):
                continue
            topic_dir_parts = rel_parts[:-1]
            if not topic_dir_parts:
                root_md_files.append(md_file)
                continue
            parts = tuple(topic_dir_parts[:3])
            topic = TOPIC_SEP.join(parts)
            topic_parts.setdefault(topic, parts)
            topic_files.setdefault(topic, []).append(md_file.stem)
            if _write_file_topic_from_folder(md_file, topic):
                updated_files += 1

    for md_file in root_md_files:
        if _write_file_topic_from_folder(md_file, None):
            updated_files += 1

    def _sort_key(item):
        topic, parts = item
        return parts

    lines = [
        "# WIKI",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"主题数量: {len(topic_parts)}",
        "",
        "## 目录",
        "",
    ]

    for topic, parts in sorted(topic_parts.items(), key=_sort_key):
        heading = "#" * (len(parts) + 1) + " " + parts[-1]
        lines.append(heading)
        summary = _topic_one_line_summary(topic, workspace_path)
        if summary:
            lines.append(f"> {summary}")
        if topic in off_topics:
            lines.append("> 综述: off")
        files = sorted(dict.fromkeys(topic_files.get(topic, [])))
        for idx, title in enumerate(files, 1):
            lines.append(f"{idx}. **{title}**")
        lines.append("")

    content = "\n".join(lines).rstrip() + "\n"
    wiki_path.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "message": f"同步完成：主题 {len(topic_parts)} 个，文件 {sum(len(v) for v in topic_files.values())} 个，更新 frontmatter {updated_files} 个",
        "topics": len(topic_parts),
        "files": sum(len(v) for v in topic_files.values()),
        "updated": updated_files,
    }
