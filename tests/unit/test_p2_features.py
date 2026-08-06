from pathlib import Path

import pytest
from sidecar.multi_source import import_transcript
from sidecar.schema_manager import SCHEMA_FILENAME

from config import config
from utils.link_indexer import (
    backfill_semantic_bidirectional,
    discover_cross_refs_for_file,
    load_links,
    purge_weak_links,
    save_links,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    notes = d / "Notes" / "AI" / "子题"
    notes.mkdir(parents=True)
    for i, title in enumerate(["源文章", "同主题A", "同主题B", "提及源", "标签友", "远房亲戚"]):
        p = notes / f"{title}.md"
        topic = "AI > 子题" if i < 3 else "AI > 其他"
        tags = "tags: [RAG, 测试]" if i == 4 else "tags: []"
        body = f"讨论 {title} 的内容。"
        if i == 3:
            body = "这里提到了源文章的核心观点。"
        p.write_text(f"---\ntopic: {topic}\n{tags}\n---\n\n# {title}\n\n{body}\n", encoding="utf-8")
    (d / "wiki").mkdir(parents=True, exist_ok=True)
    (d / SCHEMA_FILENAME).write_text(
        "# ok\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    config.workspace_path = str(d)
    return d


def test_discover_cross_refs_finds_related(workspace: Path) -> None:
    rel = "Notes/AI/子题/源文章.md"
    result = discover_cross_refs_for_file(rel, max_links=8, use_llm=False)
    assert result["success"] is True
    assert result["added"] >= 1
    links = load_links().get("links", [])
    outgoing = [l for l in links if l.get("from") == rel]
    assert len(outgoing) >= 1
    # 严格判断：启发式/LLM 候选一律 pending，等待人工确认
    assert {l.get("status") for l in outgoing} == {"pending"}


def test_discover_cross_refs_ignores_readme_notes(workspace: Path) -> None:
    readme_rel = "Notes/AI/子题/README.md"
    (workspace / readme_rel).write_text(
        "---\ntopic: AI > 子题\ntags: [RAG]\n---\n\n# README\n\n目录说明，不是知识笔记。\n",
        encoding="utf-8",
    )

    readme_result = discover_cross_refs_for_file(readme_rel, max_links=8, use_llm=False)
    assert readme_result["success"] is True
    assert readme_result["added"] == 0

    rel = "Notes/AI/子题/源文章.md"
    result = discover_cross_refs_for_file(rel, max_links=8, use_llm=False)
    assert result["success"] is True
    links = load_links().get("links", [])
    assert not any("README.md" in (l.get("from", "") + l.get("to", "")) for l in links)


def test_import_transcript(workspace: Path) -> None:
    tr = import_transcript("会议记录", "说话内容", source="Zoom")
    assert tr["success"] is True
    assert tr["path"].endswith(".md")


def test_purge_weak_links_removes_heuristic_reasons(workspace: Path) -> None:
    save_links(
        {
            "links": [
                {"from": "a.md", "to": "b.md", "reason": "共享标签「AI」", "status": "confirmed"},
                {"from": "a.md", "to": "c.md", "reason": "语义相关", "status": "confirmed"},
                {"from": "a.md", "to": "d.md", "reason": "已确认链接的邻居", "status": "confirmed"},
                {"from": "a.md", "to": "e.md", "reason": "同主题「AI > 测试」", "status": "confirmed"},
                {"from": "a.md", "to": "f.md", "reason": "正文提及「实体文档」", "status": "confirmed"},
                {"from": "g.md", "to": "h.md", "reason": "共享 4 个实体/概念", "status": "pending"},
            ],
            "last_scan": 12345,
        }
    )
    result = purge_weak_links()
    assert result["success"] is True
    assert result["total"] == 6
    assert result["removed"] == 4
    assert result["kept"] == 2
    kept = load_links().get("links", [])
    assert [l["to"] for l in kept] == ["f.md", "h.md"]
    assert load_links().get("last_scan") == 12345


def test_purge_weak_links_empty(workspace: Path) -> None:
    save_links({"links": [], "last_scan": None})
    result = purge_weak_links()
    assert result["success"] is True
    assert result["removed"] == 0


def test_backfill_semantic_bidirectional_skips_existing(workspace: Path, monkeypatch) -> None:
    import utils.link_indexer as li

    save_links(
        {
            "links": [
                {"from": "a.md", "to": "b.md", "reason": "正文提及", "status": "confirmed"},
            ],
            "last_scan": None,
        }
    )
    monkeypatch.setattr(
        li,
        "_load_all_metas_cached",
        lambda ws: {"a.md": {"title": "A"}, "b.md": {"title": "B"}, "c.md": {"title": "C"}},
    )
    monkeypatch.setattr(li, "_BIDIRECTIONAL_SHARE_MIN", 1)
    monkeypatch.setattr("sidecar.semantic.store.SemanticStore", lambda ws: object())

    def fake_names(store, cache, doc_id):
        from sidecar.semantic.ids import stable_id as _sid

        names = {
            _sid("doc", "a.md", length=24): {"x", "y", "z"},
            _sid("doc", "b.md", length=24): {"x", "y", "z"},
            _sid("doc", "c.md", length=24): {"x"},
        }
        return names.get(doc_id, set())

    monkeypatch.setattr(li, "_object_names_for", fake_names)

    result = backfill_semantic_bidirectional()
    assert result["success"] is True
    assert result["added"] == 4  # c↔a 与 c↔b 各两条；a↔b 已有边跳过
    links = load_links().get("links", [])
    pairs = {(l["from"], l["to"]) for l in links}
    assert ("a.md", "b.md") in pairs  # 原链接保留
    assert ("c.md", "a.md") in pairs and ("a.md", "c.md") in pairs
    assert ("c.md", "b.md") in pairs and ("b.md", "c.md") in pairs
