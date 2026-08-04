from __future__ import annotations

import json
from pathlib import Path

from sidecar.chunk_similarity import build_chunk_similarity_graph, load_chunk_similarity_graph


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
