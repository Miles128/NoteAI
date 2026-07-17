from __future__ import annotations

import json
from pathlib import Path

from sidecar.textutils import parse_frontmatter
from sidecar.topic_merge import merge_topics, suggest_merged_topic_names

from config import config


def _write(root: Path, topic: str, name: str) -> None:
    folder = root / "Notes" / topic
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(f"---\ntopic: {topic}\n---\n\n正文", encoding="utf-8")


def test_llm_proposes_three_topic_names(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    _write(root, "提示词工程", "甲")
    _write(root, "Prompt工程", "乙")
    monkeypatch.setattr(
        "utils.llm_utils.call_llm_raw",
        lambda *_args, **_kwargs: '{"names":[{"name":"提示词设计","reason":"覆盖两边"},{"name":"Prompt 设计","reason":"简洁"},{"name":"提示工程","reason":"通用"}]}',
    )

    result = suggest_merged_topic_names(root, ["提示词工程", "Prompt工程"])

    assert result["success"] is True
    assert [row["name"] for row in result["names"]] == ["提示词设计", "Prompt 设计", "提示工程"]


def test_topic_merge_moves_notes_and_records_aliases(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    _write(root, "提示词工程", "甲")
    _write(root, "Prompt工程", "乙")
    monkeypatch.setattr(config, "workspace_path", str(root))
    monkeypatch.setattr("sidecar.wiki_utils.sync_wiki_with_files", lambda: {"success": True})

    result = merge_topics(root, ["提示词工程", "Prompt工程"], "提示词设计")

    assert result["success"] is True
    for name in ("甲", "乙"):
        path = root / "Notes" / "提示词设计" / f"{name}.md"
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        assert meta["topic"] == "提示词设计"
    aliases = json.loads((root / ".noteai" / "topic_aliases.json").read_text(encoding="utf-8"))
    assert aliases == {"提示词工程": "提示词设计", "Prompt工程": "提示词设计"}
