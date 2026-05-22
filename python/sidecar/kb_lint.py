"""Knowledge base lint: broken links, orphans, stale surveys."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from config import config
from config.settings import NOTES_FOLDER, WORKSPACE_APP_FOLDER
from sidecar.textutils import parse_frontmatter
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


def run_kb_lint(workspace: str | None = None) -> dict:
    ws = workspace or config.workspace_path
    if not ws:
        return {"success": False, "issues": [], "summary": {}}

    root = Path(ws)
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
            issues.append(LintIssue(
                kind="orphan_topic",
                severity="warning",
                message="缺少主题（无文件夹路径且 frontmatter 无 topic）",
                file_path=rel,
            ))

        for target in _WIKILINK.findall(body):
            t = target.split("|")[-1].strip()
            if t and t not in names and not (t + ".md") in names:
                issues.append(LintIssue(
                    kind="broken_link",
                    severity="warning",
                    message=f"双向链接目标不存在: [[{target}]]",
                    file_path=rel,
                ))

    survey_by_topic: dict[str, Path] = {}
    for survey in (root / "wiki").glob("*_综述.md") if (root / "wiki").exists() else []:
        stem = survey.stem.replace("_综述", "")
        survey_by_topic[stem] = survey

    notes_by_topic_mtime: dict[str, float] = {}
    for md in _iter_notes_md(root):
        fm, _ = parse_frontmatter(md.read_text(encoding="utf-8"))
        t = topic_from_notes_path(md) or (fm.get("topic") if fm else "")
        if isinstance(t, list):
            t = t[0] if t else ""
        t = str(t).strip()
        if not t:
            continue
        leaf = t.rsplit(" > ", maxsplit=1)[-1]
        mtime = md.stat().st_mtime
        notes_by_topic_mtime[leaf] = max(notes_by_topic_mtime.get(leaf, 0), mtime)
        notes_by_topic_mtime[t] = max(notes_by_topic_mtime.get(t, 0), mtime)

    for topic_key, survey_path in survey_by_topic.items():
        note_mtime = notes_by_topic_mtime.get(topic_key, 0)
        if note_mtime and survey_path.stat().st_mtime < note_mtime - 1:
            issues.append(LintIssue(
                kind="stale_survey",
                severity="info",
                message="笔记已更新但综述可能过时",
                file_path=str(survey_path.relative_to(root)),
                topic=topic_key,
            ))

    pending_path = root / ".pending_topics.json"
    if pending_path.exists():
        try:
            import json
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            count = len(pending) if isinstance(pending, list) else 0
            if count:
                issues.append(LintIssue(
                    kind="pending_topics",
                    severity="info",
                    message=f"{count} 篇待确认主题",
                    file_path=".pending_topics.json",
                ))
        except (OSError, json.JSONDecodeError):
            pass

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
    _save_report(root, report)
    return report


def _save_report(workspace: Path, report: dict) -> None:
    p = workspace / WORKSPACE_APP_FOLDER / "lint_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    import json
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
