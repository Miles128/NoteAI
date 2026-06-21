"""Knowledge base lint: broken links, orphans, stale surveys."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from config import config
from config.constants import TOPIC_SEP
from config.settings import NOTES_FOLDER, WORKSPACE_APP_FOLDER
from sidecar.textutils import parse_frontmatter, write_frontmatter
from utils.wiki_manager import topic_from_notes_path

_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class LintIssue:
    kind: str
    severity: str
    message: str
    file_path: str = ""
    topic: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _iter_notes_md(workspace: Path) -> list[Path]:
    out: list[Path] = []
    notes = workspace / NOTES_FOLDER
    if not notes.exists():
        return out
    for md in notes.rglob("*.md"):
        if md.name.startswith("."):
            continue
        if md.name.endswith("_综述.md"):
            continue
        out.append(md)
    return out


def _all_md_names(workspace: Path) -> set[str]:
    names: set[str] = set()
    for md in workspace.rglob("*.md"):
        if md.is_file() and not md.name.startswith("."):
            names.add(md.name)
            names.add(md.stem)
    return names


def _wikilink_target_exists(target: str, names: set[str]) -> bool:
    lookup = (target or "").split("|")[0].strip()
    if not lookup:
        return True
    return lookup in names or f"{lookup}.md" in names


def _write_preserving_frontmatter(path: Path, new_body: str) -> None:
    text = path.read_text(encoding="utf-8")
    had_bom = text.startswith("\ufeff")
    meta, _ = parse_frontmatter(text)
    new_text = write_frontmatter(meta, new_body, had_bom=had_bom)
    path.write_text(new_text, encoding="utf-8")


def _remove_broken_wikilinks(body: str, names: set[str]) -> tuple[str, list[str]]:
    removed: list[str] = []

    def repl(match: re.Match[str]) -> str:
        inner = match.group(1)
        if _wikilink_target_exists(inner, names):
            return match.group(0)
        removed.append(inner)
        return ""

    new_body = _WIKILINK.sub(repl, body)
    new_body = re.sub(r"[ \t]+\n", "\n", new_body)
    new_body = re.sub(r"\n{3,}", "\n\n", new_body)
    return new_body, removed


def _build_leaf_to_topic_map(root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for md in _iter_notes_md(root):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, _ = parse_frontmatter(text)
        topic = topic_from_notes_path(md) or (fm.get("topic") if fm else "") or ""
        if isinstance(topic, list):
            topic = topic[0] if topic else ""
        topic = str(topic).strip()
        if not topic:
            continue
        leaf = topic.rsplit(TOPIC_SEP, maxsplit=1)[-1]
        prev = mapping.get(leaf)
        if not prev or len(topic) > len(prev):
            mapping[leaf] = topic
    return mapping


def _find_stale_survey_topics(root: Path) -> list[str]:
    leaf_map = _build_leaf_to_topic_map(root)
    survey_by_topic: dict[str, Path] = {}
    wiki = root / "wiki"
    if wiki.exists():
        for survey in wiki.glob("*_综述.md"):
            survey_by_topic[survey.stem.replace("_综述", "")] = survey

    notes_by_topic_mtime: dict[str, float] = {}
    for md in _iter_notes_md(root):
        try:
            fm, _ = parse_frontmatter(md.read_text(encoding="utf-8"))
        except OSError:
            continue
        t = topic_from_notes_path(md) or (fm.get("topic") if fm else "")
        if isinstance(t, list):
            t = t[0] if t else ""
        t = str(t).strip()
        if not t:
            continue
        leaf = t.rsplit(TOPIC_SEP, maxsplit=1)[-1]
        mtime = md.stat().st_mtime
        notes_by_topic_mtime[leaf] = max(notes_by_topic_mtime.get(leaf, 0), mtime)
        notes_by_topic_mtime[t] = max(notes_by_topic_mtime.get(t, 0), mtime)

    topics: list[str] = []
    seen: set[str] = set()
    for topic_key, survey_path in survey_by_topic.items():
        note_mtime = notes_by_topic_mtime.get(topic_key, 0)
        if note_mtime and survey_path.stat().st_mtime < note_mtime - 1:
            full = leaf_map.get(topic_key, topic_key)
            if full not in seen:
                seen.add(full)
                topics.append(full)
    return topics


def auto_fix_broken_links(workspace: str | Path | None = None) -> dict:
    """Remove [[broken]] wikilinks from Notes markdown."""
    from sidecar.schema_validator import check_notes_writable
    from utils.workspace_log import append_log

    ws = workspace or config.workspace_path
    if not ws:
        return {"success": False, "message": "未设置工作区", "removed": 0, "files": []}

    ok, msg = check_notes_writable("自动删除断链")
    if not ok:
        return {"success": False, "message": msg, "removed": 0, "files": []}

    root = Path(ws)
    names = _all_md_names(root)
    fixed_files: list[dict] = []
    removed_total = 0

    for md in _iter_notes_md(root):
        rel = str(md.relative_to(root))
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body = parse_frontmatter(text)
        new_body, removed = _remove_broken_wikilinks(body, names)
        if not removed:
            continue
        _write_preserving_frontmatter(md, new_body)
        removed_total += len(removed)
        fixed_files.append({"file": rel, "removed": removed})
        for target in removed:
            append_log("lint", f"已删除断链: {rel}", f"移除 [[{target}]]")

    return {
        "success": True,
        "removed": removed_total,
        "files": fixed_files,
        "file_count": len(fixed_files),
    }


def auto_refresh_stale_surveys(
    workspace: str | Path | None = None,
    *,
    send_response: Callable[[dict], None] | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict:
    """Regenerate surveys for topics whose notes are newer than survey mtime."""
    from sidecar.cascade_runner import run_cascade_for_topics
    from utils.workspace_log import append_log

    ws = workspace or config.workspace_path
    if not ws:
        return {"success": False, "message": "未设置工作区", "topics": [], "updated": 0}

    root = Path(ws)
    topics = _find_stale_survey_topics(root)
    if not topics:
        return {"success": True, "message": "无过时综述", "topics": [], "updated": 0}

    append_log("lint", f"自动更新综述: {len(topics)} 个主题", "，".join(topics[:5]))
    result = run_cascade_for_topics(
        topics,
        send_response=send_response,
        progress_cb=progress_cb,
        cancel_check=cancel_check,
    )
    updated = int(result.get("updated") or 0)
    failed = result.get("failed") or []
    if failed:
        append_log("lint", f"综述更新失败 {len(failed)} 个", "；".join(str(x) for x in failed[:5]))
    return {
        "success": not failed,
        "topics": topics,
        "updated": updated,
        "failed": failed,
        "message": result.get("message", ""),
    }


def _scan_lint_issues(root: Path) -> list[LintIssue]:
    issues: list[LintIssue] = []
    names = _all_md_names(root)

    for md in _iter_notes_md(root):
        rel = str(md.relative_to(root))
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body = parse_frontmatter(text)
        topic = topic_from_notes_path(md) or (fm.get("topic") if fm else "") or ""
        if isinstance(topic, list):
            topic = topic[0] if topic else ""
        if not str(topic).strip():
            issues.append(
                LintIssue(
                    kind="orphan_topic",
                    severity="warning",
                    message="缺少主题（无文件夹路径且 frontmatter 无 topic）",
                    file_path=rel,
                )
            )

        for target in _WIKILINK.findall(body):
            if not _wikilink_target_exists(target, names):
                issues.append(
                    LintIssue(
                        kind="broken_link",
                        severity="warning",
                        message=f"双向链接目标不存在: [[{target}]]",
                        file_path=rel,
                    )
                )

    survey_by_topic: dict[str, Path] = {}
    wiki = root / "wiki"
    if wiki.exists():
        for survey in wiki.glob("*_综述.md"):
            survey_by_topic[survey.stem.replace("_综述", "")] = survey

    notes_by_topic_mtime: dict[str, float] = {}
    for md in _iter_notes_md(root):
        try:
            fm, _ = parse_frontmatter(md.read_text(encoding="utf-8"))
        except OSError:
            continue
        t = topic_from_notes_path(md) or (fm.get("topic") if fm else "")
        if isinstance(t, list):
            t = t[0] if t else ""
        t = str(t).strip()
        if not t:
            continue
        leaf = t.rsplit(TOPIC_SEP, maxsplit=1)[-1]
        mtime = md.stat().st_mtime
        notes_by_topic_mtime[leaf] = max(notes_by_topic_mtime.get(leaf, 0), mtime)
        notes_by_topic_mtime[t] = max(notes_by_topic_mtime.get(t, 0), mtime)

    for topic_key, survey_path in survey_by_topic.items():
        note_mtime = notes_by_topic_mtime.get(topic_key, 0)
        if note_mtime and survey_path.stat().st_mtime < note_mtime - 1:
            issues.append(
                LintIssue(
                    kind="stale_survey",
                    severity="info",
                    message="笔记已更新但综述可能过时",
                    file_path=str(survey_path.relative_to(root)),
                    topic=topic_key,
                )
            )

    pending_path = root / ".pending_topics.json"
    if pending_path.exists():
        try:
            import json

            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            count = len(pending) if isinstance(pending, list) else 0
            if count:
                issues.append(
                    LintIssue(
                        kind="pending_topics",
                        severity="info",
                        message=f"{count} 篇待确认主题",
                        file_path=".pending_topics.json",
                    )
                )
        except (OSError, json.JSONDecodeError):
            pass

    return issues


def run_kb_lint(
    workspace: str | None = None,
    *,
    auto_repair: bool = True,
    auto_refresh_surveys: bool = True,
    send_response: Callable[[dict], None] | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict:
    ws = workspace or config.workspace_path
    if not ws:
        return {"success": False, "issues": [], "summary": {}}

    root = Path(ws)
    repair: dict = {}

    def _progress(stage_idx: int, stage_total: int, msg: str) -> None:
        if progress_cb:
            progress_cb(stage_idx, stage_total, msg)

    if cancel_check and cancel_check():
        return {"success": False, "issues": [], "summary": {}, "cancelled": True}

    if auto_repair:
        _progress(1, 4, "检查断链...")
        link_result = auto_fix_broken_links(root)
        repair["broken_links"] = link_result

        if cancel_check and cancel_check():
            return {"success": False, "issues": [], "summary": {}, "cancelled": True, "repair": repair}

        if auto_refresh_surveys:
            _progress(2, 4, "检查过时综述...")
            survey_result = auto_refresh_stale_surveys(
                root,
                send_response=send_response,
                progress_cb=progress_cb,
                cancel_check=cancel_check,
            )
            repair["surveys"] = survey_result

    if cancel_check and cancel_check():
        return {"success": False, "issues": [], "summary": {}, "cancelled": True, "repair": repair}

    _progress(3, 4, "扫描 Lint 问题...")
    issues = _scan_lint_issues(root)
    _progress(4, 4, "Lint 扫描完成")
    summary = {
        "total": len(issues),
        "broken_link": sum(1 for i in issues if i.kind == "broken_link"),
        "orphan_topic": sum(1 for i in issues if i.kind == "orphan_topic"),
        "stale_survey": sum(1 for i in issues if i.kind == "stale_survey"),
        "pending_topics": sum(1 for i in issues if i.kind == "pending_topics"),
    }
    report = {
        "success": True,
        "issues": [i.to_dict() for i in issues],
        "summary": summary,
    }
    if repair:
        report["repair"] = repair
    _save_report(root, report)
    return report


def _save_report(workspace: Path, report: dict) -> None:
    p = workspace / WORKSPACE_APP_FOLDER / "lint_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    import json

    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


_KIND_LABELS = {
    "broken_link": "断链",
    "orphan_topic": "缺主题",
    "stale_survey": "综述过时",
    "pending_topics": "待确认主题",
}


def _lint_issue_log_line(issue: dict) -> tuple[str, str]:
    kind = issue.get("kind") or ""
    label = _KIND_LABELS.get(kind, kind or "Lint")
    path = (issue.get("file_path") or "").strip()
    topic = (issue.get("topic") or "").strip()
    msg = (issue.get("message") or "").strip()
    if kind == "stale_survey" and topic:
        return f"{label}: {topic}", msg or path
    if path:
        return f"{label}: {path}", msg
    return label, msg


def log_lint_report(report: dict, *, max_items: int = 20) -> None:
    """Write per-issue lint lines to wiki/log.md (not just a count)."""
    from utils.workspace_log import append_log

    repair = report.get("repair") or {}
    link_fix = repair.get("broken_links") or {}
    if link_fix.get("removed"):
        append_log(
            "lint",
            f"自动删除断链 {link_fix['removed']} 处",
            f"{link_fix.get('file_count', 0)} 个文件",
        )
    survey_fix = repair.get("surveys") or {}
    if survey_fix.get("updated"):
        append_log("lint", f"自动更新综述 {survey_fix['updated']} 个主题")

    issues = report.get("issues") or []
    summary = report.get("summary") or {}
    total = int(summary.get("total") or len(issues))
    if total == 0:
        append_log("lint", "健康检查: 无问题")
        return

    breakdown: list[str] = []
    for key, label in _KIND_LABELS.items():
        count = int(summary.get(key) or 0)
        if count:
            breakdown.append(f"{label} {count}")
    append_log("lint", f"健康检查: {total} 项", "，".join(breakdown))

    for issue in issues[:max_items]:
        if not isinstance(issue, dict):
            continue
        headline, detail = _lint_issue_log_line(issue)
        append_log("lint", headline, detail)

    remaining = len(issues) - max_items
    if remaining > 0:
        append_log("lint", f"… 另有 {remaining} 项未列出（见待办或再次运行健康检查）")


def load_lint_report(workspace: str | None = None) -> dict:
    ws = workspace or config.workspace_path
    if not ws:
        return {"success": False, "issues": [], "summary": {"total": 0}}
    p = Path(ws) / WORKSPACE_APP_FOLDER / "lint_report.json"
    if not p.exists():
        return {"success": True, "issues": [], "summary": {"total": 0}, "cached": False}
    try:
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("success", True)
            data.setdefault("issues", [])
            data.setdefault("summary", {"total": len(data.get("issues", []))})
            data["cached"] = True
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"success": True, "issues": [], "summary": {"total": 0}, "cached": False}
