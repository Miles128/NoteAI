from __future__ import annotations

import json
from pathlib import Path

from sidecar.chunk_similarity import (
    _load_semantic_shares,
    build_chunk_similarity_graph,
    load_chunk_similarity_graph,
    resolve_merge_rules,
)


def _write(root: Path, topic: str, name: str, body: str) -> None:
    folder = root / "Notes" / topic
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(f"---\ntopic: {topic}\n---\n\n{body}", encoding="utf-8")


def test_similarity_scan_builds_explainable_merge_candidates(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    _write(root, "提示词工程", "提示词入门", "提示词需要清晰描述目标、上下文和输出格式。")
    _write(root, "Prompt工程", "Prompt入门", "提示词需要清晰描述目标、上下文和输出格式，并提供示例。")

    def fake_encode(texts):
        return [{"dense_vec": [1.0, 0.0, 0.0], "lexical_weights": {}} for _ in texts]

    monkeypatch.setattr("sidecar.rag.embedder.encode_documents", fake_encode)
    result = build_chunk_similarity_graph(root, top_k=6, threshold=0.68)
    graph = load_chunk_similarity_graph(root)

    assert result["candidate_count"] == 1
    assert result["topic_candidate_count"] == 1
    assert graph["candidates"][0]["pairs"][0]["coverage"] == 1.0
    assert graph["candidates"][0]["reason"] == "chunk_overlap"
    assert graph["topic_candidates"][0]["topics"] == ["Prompt工程", "提示词工程"]
    assert json.loads((root / ".noteai" / "chunk_similarity_graph.json").read_text(encoding="utf-8"))["version"] == 1


def test_merge_presets_control_candidate_discovery(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    _write(root, "人工智能", "甲笔记", "深度学习与神经网络的核心概念。")
    _write(root, "人工智能", "乙笔记", "机器学习与模型训练的基础方法。")

    def fake_encode(texts):
        out = []
        for text in texts:
            if "机器学习与模型" in str(text):
                out.append({"dense_vec": [0.82, 0.57, 0.0], "lexical_weights": {}})
            else:
                out.append({"dense_vec": [1.0, 0.0, 0.0], "lexical_weights": {}})
        return out

    monkeypatch.setattr("sidecar.rag.embedder.encode_documents", fake_encode)

    # 0.821 余弦相似度：仅 aggressive 档（overlap_sim 0.80）能发现重叠候选
    aggressive = build_chunk_similarity_graph(root, top_k=6, threshold=0.68, preset="aggressive")
    assert aggressive["candidate_count"] == 1
    graph = load_chunk_similarity_graph(root)
    assert graph["preset"] == "aggressive"
    assert graph["rules"]["overlap_sim"] == 0.80

    balanced = build_chunk_similarity_graph(root, top_k=6, threshold=0.68, preset="balanced")
    assert balanced["candidate_count"] == 0

    conservative = build_chunk_similarity_graph(root, top_k=6, threshold=0.68, preset="conservative")
    assert conservative["candidate_count"] == 0

    assert resolve_merge_rules("conservative")["overlap_sim"] == 0.90
    assert resolve_merge_rules("unknown", {"overlap_sim": 0.5})["overlap_sim"] == 0.5


def test_merge_overrides_override_preset_thresholds(tmp_path: Path, monkeypatch) -> None:
    """高级阈值覆盖（§9.2）：balanced 预设 + overlap_sim 覆盖后能发现 aggressive 才发现的候选。"""
    root = tmp_path / "ws"
    _write(root, "人工智能", "甲笔记", "深度学习与神经网络的核心概念。")
    _write(root, "人工智能", "乙笔记", "机器学习与模型训练的基础方法。")

    def fake_encode(texts):
        out = []
        for text in texts:
            if "机器学习与模型" in str(text):
                out.append({"dense_vec": [0.82, 0.57, 0.0], "lexical_weights": {}})
            else:
                out.append({"dense_vec": [1.0, 0.0, 0.0], "lexical_weights": {}})
        return out

    monkeypatch.setattr("sidecar.rag.embedder.encode_documents", fake_encode)

    with_overrides = build_chunk_similarity_graph(
        root, top_k=6, threshold=0.68, preset="balanced", rules={"overlap_sim": 0.80, "coverage": 0.50}
    )
    assert with_overrides["candidate_count"] == 1
    graph = load_chunk_similarity_graph(root)
    assert graph["preset"] == "balanced"
    assert graph["rules"]["overlap_sim"] == 0.80
    assert graph["rules"]["coverage"] == 0.50
    # 未覆盖的阈值仍保持预设值
    assert graph["rules"]["title"] == 0.82


def test_candidates_carry_semantic_share_signal(tmp_path: Path, monkeypatch) -> None:
    """候选 pair 应携带语义共享计数（来自 semantic.db），作为同源双稿证据。"""
    root = tmp_path / "ws"
    _write(root, "人工智能", "甲笔记", "深度学习与神经网络的核心概念。")
    _write(root, "人工智能", "乙笔记", "机器学习与模型训练的基础方法。")

    def fake_encode(texts):
        return [{"dense_vec": [1.0, 0.0, 0.0], "lexical_weights": {}} for _ in texts]

    def fake_semantic_shares(r: Path) -> dict:
        a = "Notes/人工智能/甲笔记.md"
        b = "Notes/人工智能/乙笔记.md"
        return {(a, b): 12}

    monkeypatch.setattr("sidecar.rag.embedder.encode_documents", fake_encode)
    monkeypatch.setattr("sidecar.chunk_similarity._load_semantic_shares", fake_semantic_shares)
    build_chunk_similarity_graph(root, top_k=6, threshold=0.68)
    graph = load_chunk_similarity_graph(root)
    pairs = [p for c in graph.get("candidates") or [] for p in c.get("pairs", [])]
    assert pairs, "应至少有一个候选 pair"
    assert max(p.get("shared_objects", 0) for p in pairs) == 12


def test_semantic_shares_degrade_gracefully(tmp_path: Path) -> None:
    """语义库缺失时应降级为空 dict，不影响候选构建。"""
    root = tmp_path / "ws"
    (root / "Notes" / "AI").mkdir(parents=True)
    (root / "Notes" / "AI" / "a.md").write_text("# a\n正文\n", encoding="utf-8")
    assert _load_semantic_shares(root) == {}
