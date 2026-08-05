from __future__ import annotations

import json
from pathlib import Path

from config import config
from utils.text_utils import parse_frontmatter
from utils.topic_merge import merge_topics, preview_topic_merge, suggest_merged_topic_names


def _write(root: Path, topic: str, name: str, body: str = "正文") -> None:
    folder = root / "Notes" / topic
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(f"---\ntopic: {topic}\n---\n\n{body}", encoding="utf-8")


def test_llm_proposes_three_topic_names(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    _write(root, "提示词工程", "甲")
    _write(root, "Prompt工程", "乙")
    monkeypatch.setattr(
        "utils.llm_utils.call_llm_raw",
        lambda *_args, **_kwargs: (
            '{"names":[{"name":"提示词设计","reason":"覆盖两边"},{"name":"Prompt 设计","reason":"简洁"},{"name":"提示工程","reason":"通用"}]}'
        ),
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


def test_preview_topic_merge_reports_notes_conflicts_and_surveys(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root, "提示词工程", "甲")
    _write(root, "Prompt工程", "乙")
    _write(root, "提示词设计", "乙")  # 目标主题已有同名文件 → 冲突
    wiki = root / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "Prompt工程_综述.md").write_text("综述", encoding="utf-8")
    (wiki / "提示词工程").mkdir(parents=True)
    (wiki / "提示词工程" / "提示词工程_综述.md").write_text("综述", encoding="utf-8")

    result = preview_topic_merge(root, ["提示词工程", "Prompt工程"], "提示词设计")

    assert result["success"] is True
    assert result["note_count"] == 2
    assert [row["name"] for row in result["conflicts"]] == ["乙.md"]
    assert result["conflicts"][0]["target"] == "Notes/提示词设计/乙.md"
    assert "wiki/Prompt工程_综述.md" in result["surveys"]
    assert "wiki/提示词工程/提示词工程_综述.md" in result["surveys"]


def test_merge_topics_renames_conflicting_files_without_overwriting(tmp_path: Path, monkeypatch) -> None:
    """同名文件不覆盖（§9.4 步骤 6）：自动改名并返回 renamed 明细。"""
    root = tmp_path / "ws"
    _write(root, "提示词工程", "甲")
    _write(root, "Prompt工程", "乙")
    _write(root, "提示词设计", "乙")  # 与待迁移文件同名
    monkeypatch.setattr(config, "workspace_path", str(root))
    monkeypatch.setattr("sidecar.wiki_utils.sync_wiki_with_files", lambda: {"success": True})

    result = merge_topics(root, ["提示词工程", "Prompt工程"], "提示词设计")

    assert result["success"] is True
    assert result["renamed"] == [{"from": "乙.md", "to": "乙_1.md"}]
    target = root / "Notes" / "提示词设计"
    # 目标主题原有文件未被覆盖
    meta, _ = parse_frontmatter((target / "乙.md").read_text(encoding="utf-8"))
    assert meta["topic"] == "提示词设计"
    assert (target / "乙_1.md").exists()


def test_suggest_names_reads_survey_and_representative_chunks(tmp_path: Path, monkeypatch) -> None:
    """命名输入增强（§9.4 步骤 2）：prompt 包含主题综述与代表性 Chunk。"""
    root = tmp_path / "ws"
    _write(root, "提示词工程", "甲", "提示词需要清晰描述目标。")
    _write(root, "Prompt工程", "乙", "提示词需要提供示例。")
    wiki = root / "wiki"
    wiki.mkdir(parents=True)
    (wiki / "提示词工程_综述.md").write_text("---\n---\n\n本主题覆盖提示词的目标描述与示例设计。", encoding="utf-8")
    graph_dir = root / ".noteai"
    graph_dir.mkdir(parents=True)
    (graph_dir / "chunk_similarity_graph.json").write_text(
        json.dumps(
            {
                "chunks": [
                    {"topic": "提示词工程", "content": "代表性片段一：清晰描述目标与输出格式。"},
                    {"topic": "Prompt工程", "content": "代表性片段二：示例驱动的提示词编写。"},
                    {"topic": "无关主题", "content": "不应进入 prompt 的片段。"},
                ]
            }
        ),
        encoding="utf-8",
    )
    captured: dict = {}

    def fake_llm(prompt, **_kwargs):
        captured["prompt"] = prompt
        return '{"names":[{"name":"提示词设计","reason":"覆盖两边"}]}'

    monkeypatch.setattr("utils.llm_utils.call_llm_raw", fake_llm)

    result = suggest_merged_topic_names(root, ["提示词工程", "Prompt工程"])

    assert result["success"] is True
    prompt = captured["prompt"]
    assert "主题综述「提示词工程」" in prompt
    assert "本主题覆盖提示词的目标描述" in prompt
    assert "代表性片段一" in prompt
    assert "代表性片段二" in prompt
    assert "不应进入 prompt 的片段" not in prompt
