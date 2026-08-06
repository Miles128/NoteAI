import re
from pathlib import Path

import yaml

from config import config
from config.constants import TOPIC_SEP
from utils.logger import logger
from utils.text_utils import parse_frontmatter
from utils.wiki_manager import _get_wiki_path, collect_survey_off_topics

TAGS_START = "<!-- NOTEAI_TAGS_START -->"
TAGS_END = "<!-- NOTEAI_TAGS_END -->"
_TAG_LINE = re.compile(r"^- \*\*(.+?)\*\*(?::\s*(.*))?$")


def read_wiki_tag_map(wiki_path: Path) -> dict[str, list[str]]:
    """Read the managed tag database embedded in WIKI.md."""
    if not wiki_path.exists():
        return {}
    try:
        text = wiki_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if TAGS_START not in text or TAGS_END not in text:
        return {}
    section = text.split(TAGS_START, 1)[1].split(TAGS_END, 1)[0]
    result: dict[str, list[str]] = {}
    for raw_line in section.splitlines():
        match = _TAG_LINE.match(raw_line.strip())
        if not match:
            continue
        tag = match.group(1).strip()
        files = re.findall(r"`([^`]+\.md)`", match.group(2) or "")
        if tag:
            result[tag] = files
    return result


def _render_tag_section(tag_map: dict[str, list[str]]) -> list[str]:
    lines = [TAGS_START, "## 标签索引", ""]
    for tag, files in sorted(tag_map.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        refs = ", ".join(f"`{path}`" for path in sorted(dict.fromkeys(files)))
        lines.append(f"- **{tag}**" + (f": {refs}" if refs else ""))
    lines.extend(["", TAGS_END])
    return lines


def _read_legacy_tag_names(wiki_path: Path) -> set[str]:
    legacy_path = wiki_path.parent / "tags.md"
    if not legacy_path.exists():
        return set()
    try:
        return {
            line[3:].strip()
            for line in legacy_path.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ") and line[3:].strip()
        }
    except OSError:
        return set()


def write_wiki_tag_map(wiki_path: Path, tag_map: dict[str, list[str]]) -> bool:
    """Replace only the managed tag section, preserving the topic database."""
    if not wiki_path.exists():
        return False
    text = wiki_path.read_text(encoding="utf-8")
    section = "\n".join(_render_tag_section(tag_map))
    if TAGS_START in text and TAGS_END in text:
        prefix = text.split(TAGS_START, 1)[0].rstrip()
        suffix = text.split(TAGS_END, 1)[1].lstrip("\n")
        content = prefix + "\n\n" + section + "\n"
        if suffix:
            content += suffix
    else:
        content = text.rstrip() + "\n\n" + section + "\n"
    if content == text:
        return False
    wiki_path.write_text(content, encoding="utf-8")
    return True


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
    known_tags = set(read_wiki_tag_map(wiki_path)) | _read_legacy_tag_names(wiki_path)
    tag_files: dict[str, list[str]] = {tag: [] for tag in known_tags}
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
            from sidecar.workspace_meta import is_workspace_meta_path

            if is_workspace_meta_path(md_file):
                continue
            try:
                meta, _ = parse_frontmatter(md_file.read_text(encoding="utf-8"))
                raw_tags = (meta or {}).get("tags", [])
                if isinstance(raw_tags, str):
                    raw_tags = [raw_tags]
                for raw_tag in raw_tags if isinstance(raw_tags, list) else []:
                    tag = str(raw_tag).strip()
                    if tag:
                        tag_files.setdefault(tag, []).append(str(md_file.relative_to(workspace_path)))
            except OSError:
                pass
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
        # 根目录 README/知识图谱是导航元文档，不强制移除 topic
        if md_file.stem.casefold() in ("readme", "知识图谱"):
            continue
        if _write_file_topic_from_folder(md_file, None):
            updated_files += 1

    def _sort_key(item):
        topic, parts = item
        return parts

    lines = [
        "# WIKI",
        "",
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

    lines.extend(_render_tag_section(tag_files))

    content = "\n".join(lines).rstrip() + "\n"
    previous = wiki_path.read_text(encoding="utf-8") if wiki_path.exists() else ""
    changed = previous != content
    if changed:
        wiki_path.write_text(content, encoding="utf-8")
    legacy_tags_path = wiki_path.parent / "tags.md"
    if legacy_tags_path.exists():
        try:
            legacy_tags_path.unlink()
        except OSError as e:
            logger.warning(f"[wiki_sync] remove legacy tags.md failed: {e}")

    return {
        "success": True,
        "message": f"同步完成：主题 {len(topic_parts)} 个，文件 {sum(len(v) for v in topic_files.values())} 个，更新 frontmatter {updated_files} 个",
        "topics": len(topic_parts),
        "files": sum(len(v) for v in topic_files.values()),
        "updated": updated_files,
        "changed": changed,
        "tags": len(tag_files),
    }
