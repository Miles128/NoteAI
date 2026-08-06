import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sidecar.handlers.topics_handler import (
    TopicsHandler,
    _parse_heading_comment,
    parse_topic_wiki_meta,
)
from sidecar.semantic.ids import stable_id

from config import config
from config.constants import TOPIC_SEP, WORKSPACE_APP_FOLDER


@pytest.fixture
def workspace(tmp_path: Path):
    root = tmp_path / "workspace"
    (root / "Notes").mkdir(parents=True)
    old = config.workspace_path
    config.workspace_path = str(root)
    yield root
    config.workspace_path = old


@pytest.fixture(autouse=True)
def _reset_pending_maintenance():
    TopicsHandler._pending_maintenance_last_scheduled.clear()


def _make_handler() -> TopicsHandler:
    srv = SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None))
    return TopicsHandler(srv)


def _write_wiki(root: Path, content: str) -> None:
    wiki_dir = root / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "WIKI.md").write_text(content, encoding="utf-8")


def _write_state(root: Path, topic: str, generated_at: str, documents: int = 0) -> Path:
    state_dir = root / WORKSPACE_APP_FOLDER / "compiler" / "topic_states"
    state_dir.mkdir(parents=True, exist_ok=True)
    topic_id = stable_id("top", topic.casefold())
    path = state_dir / f"{topic_id}.json"
    path.write_text(
        json.dumps(
            {
                "topic": topic,
                "generated_at": generated_at,
                "input_hash": "hash",
                "stats": {"documents": documents, "claims": 0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _make_note(root: Path, topic: str, name: str = "note") -> Path:
    topic_dir = root / "Notes" / topic.replace(TOPIC_SEP, "/")
    topic_dir.mkdir(parents=True, exist_ok=True)
    note = topic_dir / f"{name}.md"
    note.write_text(f"---\ntopic: {topic}\n---\n正文", encoding="utf-8")
    return note


def _set_mtime(path: Path, ts: float) -> None:
    os.utime(path, (ts, ts))


def test_topic_meta_not_exists(workspace: Path) -> None:
    handler = _make_handler()
    assert handler._topic_meta({"topic": "不存在"}) == {"exists": False}


def test_topic_meta_requires_topic_param(workspace: Path) -> None:
    handler = _make_handler()
    result = handler._topic_meta({})
    assert result["success"] is False


def test_topic_meta_reads_wiki_meta_and_state(workspace: Path) -> None:
    topic = "技术 > Python"
    _write_wiki(
        workspace,
        '# WIKI\n\n## 技术\n\n### Python\n<!-- {"source_count": 2, "conflict_pending_count": 1} -->\n1. **note**\n',
    )
    _write_state(workspace, topic, "2020-01-01T00:00:00+00:00", documents=2)
    note = _make_note(workspace, topic)
    _set_mtime(note, datetime(2019, 1, 1, tzinfo=timezone.utc).timestamp())

    result = _make_handler()._topic_meta({"topic": topic})

    assert result["exists"] is True
    assert result["source_count"] == 2
    assert result["conflict_pending_count"] == 1
    assert result["compiled_at"] == "2020-01-01T00:00:00+00:00"
    assert result["is_stale"] is False


def test_topic_meta_stale_when_note_newer_than_compiled(workspace: Path) -> None:
    topic = "技术 > Python"
    _write_state(workspace, topic, "2020-01-01T00:00:00+00:00")
    note = _make_note(workspace, topic)
    _set_mtime(note, time.time())

    result = _make_handler()._topic_meta({"topic": topic})

    assert result["exists"] is True
    assert result["is_stale"] is True


def test_topic_meta_stale_when_never_compiled(workspace: Path) -> None:
    _make_note(workspace, "随笔")

    result = _make_handler()._topic_meta({"topic": "随笔"})

    assert result["exists"] is True
    assert result["compiled_at"] is None
    assert result["is_stale"] is True


def test_parse_heading_comment_json_and_key_value() -> None:
    assert _parse_heading_comment(' {"source_count": 3} ') == {"source_count": 3}
    assert _parse_heading_comment("source_count: 3\ngenerated_at: 2026-01-01T00:00:00+00:00") == {
        "source_count": "3",
        "generated_at": "2026-01-01T00:00:00+00:00",
    }


def test_parse_topic_wiki_meta_nested_topic(workspace: Path) -> None:
    _write_wiki(
        workspace,
        "# WIKI\n\n## 技术\n\n### Python\n"
        "<!-- source_count: 2\nconflict_pending_count: 1 -->\n"
        "1. **note**\n\n### Go\n1. **other**\n",
    )

    meta = parse_topic_wiki_meta(f"技术{TOPIC_SEP}Python")

    assert meta == {"source_count": "2", "conflict_pending_count": "1"}
    assert parse_topic_wiki_meta("技术 > Go") == {}
    assert parse_topic_wiki_meta("不存在") is None


def test_topic_tree_includes_stale_topics(workspace: Path) -> None:
    fresh_topic = "新鲜主题"
    stale_topic = "过期主题"
    _write_state(workspace, stale_topic, "2020-01-01T00:00:00+00:00")
    _write_state(workspace, fresh_topic, "2100-01-01T00:00:00+00:00")
    stale_note = _make_note(workspace, stale_topic)
    _set_mtime(stale_note, time.time())
    fresh_note = _make_note(workspace, fresh_topic)
    _set_mtime(fresh_note, datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())

    result = _make_handler()._get_topic_tree_3tier({})

    assert result["success"] is True
    assert result["stale_topics"] == [stale_topic]


def test_stale_scan_counts_descendant_notes_and_skips_surveys(workspace: Path) -> None:
    """单次遍历 stale 扫描：子主题笔记计入父主题 mtime，综述文件不计入。"""
    parent = "技术 > Python"
    fresh = "新鲜综述主题"
    _write_state(workspace, parent, "2020-01-01T00:00:00+00:00")
    _write_state(workspace, fresh, "2020-01-01T00:00:00+00:00")

    child_note = _make_note(workspace, f"{parent}{TOPIC_SEP}异步", name="child")
    _set_mtime(child_note, time.time())

    survey_note = _make_note(workspace, fresh, name="新鲜综述主题_综述")
    _set_mtime(survey_note, time.time())

    stale = _make_handler()._collect_stale_topics(str(workspace))

    assert stale == [parent]


def test_stale_scan_matches_by_frontmatter_topics_list(workspace: Path) -> None:
    """单次遍历 stale 扫描：目录不匹配但 frontmatter topics 列表归属主题的笔记也应计入。"""
    topic = "仅Frontmatter归属"
    _write_state(workspace, topic, "2020-01-01T00:00:00+00:00")
    stray = workspace / "Notes" / "unrelated-dir" / "note.md"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text(f"---\ntopics:\n  - {topic}\n---\n正文", encoding="utf-8")
    _set_mtime(stray, time.time())

    stale = _make_handler()._collect_stale_topics(str(workspace))

    assert stale == [topic]


def test_topic_meta_route_registered(workspace: Path) -> None:
    registered: list[str] = []

    class Router:
        def register(self, name, fn):
            registered.append(name)

    _make_handler().register_routes(Router())

    assert "topic_meta" in registered


def test_topic_meta_conflict_count_from_review_queue(workspace: Path) -> None:
    topic = "冲突主题"
    db_path = workspace / WORKSPACE_APP_FOLDER / "compiler" / "semantic.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    note = _make_note(workspace, topic)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE documents(id TEXT PRIMARY KEY, topic TEXT);
            CREATE TABLE blocks(id TEXT PRIMARY KEY, document_id TEXT);
            CREATE TABLE evidence(id TEXT PRIMARY KEY, claim_id TEXT, block_id TEXT, status TEXT);
            CREATE TABLE claims(id TEXT PRIMARY KEY);
            CREATE TABLE review_queue(id TEXT PRIMARY KEY, item_kind TEXT, payload_json TEXT,
                                      reason TEXT, status TEXT, created_at TEXT);
            """
        )
        conn.execute("INSERT INTO documents(id, topic) VALUES('d1', ?)", (topic,))
        conn.execute("INSERT INTO blocks(id, document_id) VALUES('b1', 'd1')")
        conn.execute("INSERT INTO evidence(id, claim_id, block_id, status) VALUES('e1', 'ca', 'b1', 'active')")
        conn.execute("INSERT INTO claims(id) VALUES('ca')")
        conn.execute(
            "INSERT INTO review_queue(id, item_kind, payload_json, reason, status, created_at) "
            "VALUES('rq1', 'claim_conflict', ?, 'r', 'pending', 'now')",
            (json.dumps({"claim_a_id": "ca", "claim_b_id": "cb"}),),
        )
        conn.commit()
    finally:
        conn.close()

    result = _make_handler()._topic_meta({"topic": topic})

    assert result["exists"] is True
    assert result["conflict_pending_count"] == 1
    assert note.is_file()
