"""Review and merge duplicate notes without changing the originals."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from config.settings import NOTES_FOLDER, WORKSPACE_APP_FOLDER
from utils.helpers import sanitize_filename
from utils.text_utils import parse_frontmatter, write_frontmatter

_STATE_FILE = "duplicate_resolutions.json"


def _root(workspace: str | Path) -> Path:
    return Path(workspace).resolve()


def _safe_note(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    notes = (root / NOTES_FOLDER).resolve()
    path.relative_to(notes)
    if path.suffix.lower() != ".md" or not path.is_file():
        raise ValueError("只能处理 Notes/ 下存在的 Markdown 笔记")
    return path


def _body_hash(body: str) -> str:
    normalized = re.sub(r"\s+", "", body).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _pair_key(left: str, right: str) -> str:
    return "|".join(sorted((left, right)))


def _state_path(root: Path) -> Path:
    return root / WORKSPACE_APP_FOLDER / _STATE_FILE


def _load_state(root: Path) -> dict:
    try:
        data = json.loads(_state_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(root: Path, data: dict) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def is_pair_resolved(root: Path, left: str, right: str, left_body: str, right_body: str) -> bool:
    entry = _load_state(root).get(_pair_key(left, right))
    if not isinstance(entry, dict):
        return False
    direct = entry.get("left_hash") == _body_hash(left_body) and entry.get("right_hash") == _body_hash(right_body)
    reverse = entry.get("left_hash") == _body_hash(right_body) and entry.get("right_hash") == _body_hash(left_body)
    return direct or reverse


def _mark_pair_resolved(root: Path, left: str, right: str, left_body: str, right_body: str) -> None:
    data = _load_state(root)
    data[_pair_key(left, right)] = {
        "left_hash": _body_hash(left_body),
        "right_hash": _body_hash(right_body),
    }
    _save_state(root, data)


def get_duplicate_review(workspace: str | Path, file_path: str, related_file: str) -> dict:
    root = _root(workspace)
    left = _safe_note(root, file_path)
    right = _safe_note(root, related_file)
    left_meta, left_body = parse_frontmatter(left.read_text(encoding="utf-8"))
    right_meta, right_body = parse_frontmatter(right.read_text(encoding="utf-8"))
    return {
        "success": True,
        "file_path": file_path,
        "related_file": related_file,
        "primary": {"title": left.stem, "meta": left_meta or {}, "body": left_body},
        "related": {"title": right.stem, "meta": right_meta or {}, "body": right_body},
        "exact": _body_hash(left_body) == _body_hash(right_body),
    }


def is_merge_group_resolved(root: Path, file_paths: list[str]) -> bool:
    try:
        notes = [_safe_note(root, rel) for rel in file_paths]
        bodies = [parse_frontmatter(note.read_text(encoding="utf-8"))[1] for note in notes]
    except (OSError, ValueError):
        return True
    return all(
        is_pair_resolved(root, file_paths[i], file_paths[j], bodies[i], bodies[j])
        for i in range(len(file_paths))
        for j in range(i + 1, len(file_paths))
    )


def _unique_blocks(primary: str, related: str) -> list[str]:
    existing = {re.sub(r"\s+", "", block).casefold() for block in primary.split("\n\n") if block.strip()}
    return [
        block.strip()
        for block in related.split("\n\n")
        if block.strip() and re.sub(r"\s+", "", block).casefold() not in existing
    ]


def merge_duplicate_notes(
    workspace: str | Path,
    file_path: str,
    related_file: str,
    title: str = "",
) -> dict:
    root = _root(workspace)
    primary = _safe_note(root, file_path)
    related = _safe_note(root, related_file)
    primary_meta, primary_body = parse_frontmatter(primary.read_text(encoding="utf-8"))
    _, related_body = parse_frontmatter(related.read_text(encoding="utf-8"))

    merged_body = primary_body.strip()
    additions = _unique_blocks(primary_body, related_body)
    left_rel = str(primary.relative_to(root))
    right_rel = str(related.relative_to(root))
    if not additions:
        _mark_pair_resolved(root, left_rel, right_rel, primary_body, related_body)
        return {
            "success": True,
            "output_path": left_rel,
            "added_blocks": 0,
            "message": "两篇笔记内容完全相同，已标记为已处理，未创建重复整合稿",
        }
    if additions:
        merged_body = merged_body + "\n\n" + "\n\n".join(additions)

    meta = dict(primary_meta or {})
    for key in ("source", "source_sha256", "origin"):
        meta.pop(key, None)
    output_title = sanitize_filename(title.strip() or f"{primary.stem}（整合）") or f"{primary.stem}-整合"
    output = primary.parent / f"{output_title}.md"
    counter = 1
    while output.exists() and output.resolve() not in {primary.resolve(), related.resolve()}:
        output = primary.parent / f"{output_title}_{counter}.md"
        counter += 1
    if output.resolve() in {primary.resolve(), related.resolve()}:
        return {"success": False, "message": "整合稿名称与原笔记冲突，请换一个名称"}

    output.write_text(write_frontmatter(meta, merged_body), encoding="utf-8")
    _mark_pair_resolved(root, left_rel, right_rel, primary_body, related_body)
    return {
        "success": True,
        "output_path": str(output.relative_to(root)),
        "added_blocks": len(additions),
        "message": "整合稿已创建，原笔记未修改",
    }


def merge_note_group(
    workspace: str | Path,
    file_paths: list[str],
    title: str = "",
    *,
    delete_authorized: bool = False,
) -> dict:
    """Generate one AI synthesis from 2-5 notes; deletion requires this-call authorization."""
    if not 2 <= len(file_paths) <= 5 or len(set(file_paths)) != len(file_paths):
        return {"success": False, "message": "一次只能整合 2–5 篇不同笔记"}
    root = _root(workspace)
    notes = [_safe_note(root, rel) for rel in file_paths]
    parsed = [parse_frontmatter(note.read_text(encoding="utf-8")) for note in notes]
    bodies = [body for _, body in parsed]
    source_blocks = "\n\n".join(
        f'<source index="{index + 1}" path="{file_paths[index]}">\n{body}\n</source>'
        for index, body in enumerate(bodies)
    )
    prompt = f"""你是 NoteAI 的知识整合器。把以下笔记整合成一篇结构清晰的 Markdown。
规则：删除重复表达；保留互补信息；日期、数字、结论或否定关系冲突时不得裁决，必须建立“## 观点差异（待确认）”并逐项标注 [来源N]；每个主要段落末尾标注来源；不要编造。

{source_blocks}
"""
    from utils.llm_utils import call_llm_raw

    merged_body = call_llm_raw(prompt, temperature=0.2).strip()
    if not merged_body:
        return {"success": False, "message": "AI 未返回整合内容"}
    has_conflicts = "观点差异" in merged_body or "待确认冲突" in merged_body
    primary_meta = dict(parsed[0][0] or {})
    for key in ("source", "source_sha256", "origin"):
        primary_meta.pop(key, None)
    primary_meta["merged_from"] = file_paths
    primary_meta["merge_conflicts"] = has_conflicts
    output_title = sanitize_filename(title.strip() or f"{notes[0].stem}（整合）") or f"{notes[0].stem}-整合"
    output = notes[0].parent / f"{output_title}.md"
    counter = 1
    while output.exists() or output.resolve() in {note.resolve() for note in notes}:
        output = notes[0].parent / f"{output_title}_{counter}.md"
        counter += 1
    output.write_text(write_frontmatter(primary_meta, merged_body), encoding="utf-8")

    for left_index, left in enumerate(notes):
        for right_index in range(left_index + 1, len(notes)):
            _mark_pair_resolved(
                root, file_paths[left_index], file_paths[right_index], bodies[left_index], bodies[right_index]
            )

    deleted: list[str] = []
    if delete_authorized and not has_conflicts:
        from send2trash import send2trash

        for note, rel in zip(notes, file_paths, strict=True):
            send2trash(str(note))
            deleted.append(rel)
    return {
        "success": True,
        "output_path": str(output.relative_to(root)),
        "has_conflicts": has_conflicts,
        "deleted": deleted,
        "message": "整合稿已创建" + ("；存在待确认冲突，原笔记已保留" if has_conflicts else ""),
    }
