from __future__ import annotations

import json
from pathlib import Path

from sidecar.chunk_similarity import build_chunk_similarity_graph, load_chunk_similarity_graph, resolve_merge_rules


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
