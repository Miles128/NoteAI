"""笔记合并建议分析器的单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from config import config
from utils.note_merge_analyzer import (
    _A_LEVEL,
    _B_LEVEL,
    _C_LEVEL,
    _redirect_links,
    get_note_merge_suggestions,
    is_index_ready,
    merge_suggested_notes,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    previous = config.workspace_path
    d = tmp_path / "ws"
    (d / "Notes").mkdir(parents=True)
    (d / ".noteai" / "rag_index").mkdir(parents=True)
    config.workspace_path = str(d)
    yield d
    config.workspace_path = previous


def _fake_vectors(monkeypatch, rels, sims):
    """构造 N 个向量的相似度布局：sims[i][j] 为期望相似度。"""
    n = len(rels)
    rng = np.random.default_rng(42)
    mat = rng.normal(size=(n, 16)).astype(np.float32)
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    # 用共旋法近似对齐目标相似度：简单起见用目标矩阵的 Cholesky 因子
    target = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            target[i, j] = sims[i][j] if i != j else 1.0
    target = (target + target.T) / 2
    try:
        L = np.linalg.cholesky(target + np.eye(n) * 1e-6)
    except np.linalg.LinAlgError:
        L = np.eye(n)
    # 直接用 Gram 结构：vec_i · vec_j ≈ target[i,j]
    gram = target
    eigvals, eigvecs = np.linalg.eigh(gram)
    eigvals = np.clip(eigvals, 1e-6, None)
    B = eigvecs @ np.diag(np.sqrt(eigvals))
    mat = B.astype(np.float32)
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    monkeypatch.setattr(
        "utils.note_merge_analyzer._load_file_vectors",
        lambda: (rels, mat),
    )
    # stale 过滤需要文件真实存在；在 workspace 内创建占位文件
    from config import config

    ws = config.workspace_path
    if ws:
        for r in rels:
            p = Path(ws) / r
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text("placeholder", encoding="utf-8")


def test_get_suggestions_levels(workspace: Path, monkeypatch) -> None:
    rels = ["Notes/A.md", "Notes/B.md", "Notes/C.md", "Notes/D.md"]
    # A<->B 高度相似 (A级), B<->C 中度 (B级), C<->D 低 (C级以下)
    sims = [
        [1.0, 0.97, 0.93, 0.50],
        [0.97, 1.0, 0.94, 0.55],
        [0.93, 0.94, 1.0, 0.60],
        [0.50, 0.55, 0.60, 1.0],
    ]
    _fake_vectors(monkeypatch, rels, sims)
    monkeypatch.setattr(
        "utils.note_merge_analyzer._load_semantic_shares",
        lambda: {("Notes/A.md", "Notes/B.md"): 12, ("Notes/B.md", "Notes/C.md"): 4},
    )

    result = get_note_merge_suggestions()
    assert result["success"] is True
    assert result["has_index"] is True
    assert result["has_semantics"] is True
    sugs = {s["file_a"] + "|" + s["file_b"]: s for s in result["suggestions"]}
    assert sugs["Notes/A.md|Notes/B.md"]["level"] == "A"
    assert sugs["Notes/A.md|Notes/B.md"]["shared_objects"] == 12
    assert sugs["Notes/B.md|Notes/C.md"]["level"] == "B"
    assert sugs["Notes/B.md|Notes/C.md"]["shared_objects"] == 4
    # A->B 分数最高应排前
    assert result["suggestions"][0]["level"] == "A"


def test_get_suggestions_no_index(workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "utils.note_merge_analyzer._load_file_vectors",
        lambda: ([], None),
    )
    result = get_note_merge_suggestions()
    assert result["success"] is False
    assert result["suggestions"] == []
    assert "索引" in result["message"]


def test_get_suggestions_no_semantics(workspace: Path, monkeypatch) -> None:
    rels = ["Notes/A.md", "Notes/B.md"]
    sims = [[1.0, 0.93], [0.93, 1.0]]
    _fake_vectors(monkeypatch, rels, sims)
    monkeypatch.setattr("utils.note_merge_analyzer._load_semantic_shares", lambda: {})
    result = get_note_merge_suggestions()
    assert result["success"] is True
    assert result["has_semantics"] is False
    assert result["total"] >= 1
    assert result["suggestions"][0]["shared_objects"] == 0


def test_min_score_filter(workspace: Path, monkeypatch) -> None:
    rels = ["Notes/A.md", "Notes/B.md", "Notes/C.md"]
    sims = [
        [1.0, 0.97, 0.90],
        [0.97, 1.0, 0.91],
        [0.90, 0.91, 1.0],
    ]
    _fake_vectors(monkeypatch, rels, sims)
    result = get_note_merge_suggestions(min_score=_A_LEVEL)
    assert result["total"] == 1
    assert result["suggestions"][0]["file_a"] == "Notes/A.md"


def test_stale_files_filtered(workspace: Path, monkeypatch) -> None:
    """索引中存在但磁盘已删除的文件应从分析中剔除。"""
    rels = ["Notes/A.md", "Notes/B.md", "Notes/被删.md"]
    sims = [
        [1.0, 0.97, 0.96],
        [0.97, 1.0, 0.95],
        [0.96, 0.95, 1.0],
    ]
    _fake_vectors(monkeypatch, rels, sims)
    # _fake_vectors 已创建全部占位文件；模拟"被删.md"已删除
    (workspace / "Notes" / "被删.md").unlink()
    result = get_note_merge_suggestions()
    assert result["success"] is True
    assert result["stale_count"] == 1
    for s in result["suggestions"]:
        assert "被删" not in s["file_a"]
        assert "被删" not in s["file_b"]


def test_threshold_constants() -> None:
    assert _A_LEVEL > _B_LEVEL > _C_LEVEL


def test_is_index_ready(workspace: Path) -> None:
    assert is_index_ready() is False
    (workspace / ".noteai" / "rag_index" / "manifest.json").write_text("{}", encoding="utf-8")
    assert is_index_ready() is True


def test_merge_suggested_notes_delegates(workspace: Path, monkeypatch) -> None:
    """merge_suggested_notes 应委托 merge_note_group 并在删除后重定向链接。"""
    calls: list[dict] = []

    def fake_merge(workspace, file_paths, title, *, delete_authorized=False):
        calls.append(
            {"workspace": workspace, "file_paths": file_paths, "title": title, "delete_authorized": delete_authorized}
        )
        return {
            "success": True,
            "output_path": "Notes/整合.md",
            "deleted": ["Notes/A.md", "Notes/B.md"],
            "message": "整合稿已创建",
        }

    monkeypatch.setattr("sidecar.duplicate_review.merge_note_group", fake_merge)
    # 预置 .links.json：两条指向 A/B 的链接
    (workspace / ".links.json").write_text(
        json.dumps(
            {
                "links": [
                    {"from": "Notes/X.md", "to": "Notes/A.md", "reason": "r", "status": "confirmed"},
                    {"from": "Notes/B.md", "to": "Notes/Y.md", "reason": "r", "status": "confirmed"},
                    {"from": "Notes/A.md", "to": "Notes/B.md", "reason": "r", "status": "confirmed"},
                ],
                "last_scan": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = merge_suggested_notes(["Notes/A.md", "Notes/B.md"], title="整合", delete_authorized=True)
    assert result["success"] is True
    assert calls[0]["delete_authorized"] is True
    assert calls[0]["title"] == "整合"

    links = json.loads((workspace / ".links.json").read_text(encoding="utf-8"))["links"]
    # 4 条链接中指向 A/B 的 4 端全部重定向到整合稿
    for link in links:
        assert link["from"] in {"Notes/X.md", "Notes/整合.md"}
        assert link["to"] in {"Notes/整合.md", "Notes/Y.md"}


def test_merge_suggested_notes_rejects_count(workspace: Path) -> None:
    result = merge_suggested_notes(["Notes/A.md"])
    assert result["success"] is False


def test_redirect_links(workspace: Path) -> None:
    (workspace / ".links.json").write_text(
        json.dumps(
            {
                "links": [
                    {"from": "a.md", "to": "old.md", "reason": "r"},
                    {"from": "old.md", "to": "b.md", "reason": "r"},
                    {"from": "c.md", "to": "d.md", "reason": "r"},
                ]
            }
        ),
        encoding="utf-8",
    )
    _redirect_links(["old.md"], "new.md")
    links = json.loads((workspace / ".links.json").read_text(encoding="utf-8"))["links"]
    assert links[0]["to"] == "new.md"
    assert links[1]["from"] == "new.md"
    assert links[2] == {"from": "c.md", "to": "d.md", "reason": "r"}
