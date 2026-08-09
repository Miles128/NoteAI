"""语义关系星云图数据查询测试（graph_data.py）。"""

from __future__ import annotations

from pathlib import Path

from sidecar.semantic.graph_data import get_semantic_graph_data
from sidecar.semantic.store import SemanticStore

_OBJECTS = [
    ("entities", "entity-1", "BM25", "algorithm", 0.9),
    ("entities", "entity-2", "LangChain", "product", 0.9),
    ("entities", "entity-3", "孤立实体", "other", 0.9),
    ("concepts", "concept-1", "混合检索", "", 0.95),
]

_DOCS = [
    ("doc-1", "Notes/AI/RAG.md", "RAG", "AI > RAG"),
    ("doc-2", "Notes/AI/LangChain.md", "LangChain", "AI > RAG"),
    ("doc-3", "Notes/其他/杂记.md", "杂记", "其他"),
]


def _seed_store(workspace: Path) -> None:
    store = SemanticStore(workspace)
    store.initialize()
    with store.connect() as conn:
        for doc_id, path, title, topic in _DOCS:
            conn.execute(
                """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
                   VALUES(?, ?, 'h', ?, ?, '2026-07-17T10:00:00Z')""",
                (doc_id, path, title, topic),
            )
        # 三个块：doc-1 两块、doc-2 一块
        blocks = [
            ("block-1", "doc-1", '["检索"]', "a"),
            ("block-2", "doc-1", '["对比"]', "b"),
            ("block-3", "doc-2", '["集成"]', "c"),
        ]
        for block_id, doc_id, heading, content in blocks:
            conn.execute(
                """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                      content, content_hash, start_line, end_line)
                   VALUES(?, ?, 'paragraph', ?, 0, ?, 'h', 1, 1)""",
                (block_id, doc_id, heading, content),
            )
        for table, obj_id, name, etype, conf in _OBJECTS:
            if table == "entities":
                conn.execute(
                    """INSERT INTO entities(id, canonical_name, entity_type, description,
                                            confidence, status)
                       VALUES(?, ?, ?, '描述', ?, 'active')""",
                    (obj_id, name, etype, conf),
                )
            else:
                conn.execute(
                    """INSERT INTO concepts(id, canonical_name, description, confidence, status)
                       VALUES(?, ?, '描述', ?, 'active')""",
                    (obj_id, name, conf),
                )
        # mentions：entity-1 与 entity-2 共现于 block-1（同块），entity-1 单现于 block-2，
        # entity-2 单现于 block-3；concept-1 单现于 block-1。
        mentions = [
            ("entity-1", "entity", "block-1"),
            ("entity-2", "entity", "block-1"),
            ("entity-1", "entity", "block-2"),
            ("entity-2", "entity", "block-3"),
            ("concept-1", "concept", "block-1"),
        ]
        for obj_id, kind, block_id in mentions:
            conn.execute(
                "INSERT INTO semantic_mentions(object_id, object_kind, block_id) VALUES(?, ?, ?)",
                (obj_id, kind, block_id),
            )
        # relations：entity-1 ↔ entity-2 共享 block-1（weight=1）
        conn.execute(
            """INSERT INTO relations(id, source_id, relation_type, target_id, confidence, block_id)
               VALUES('rel-1', 'entity-1', 'RELATED_TO', 'entity-2', 0.8, 'block-1')"""
        )


def test_all_scope_returns_top_objects_and_relation_edges(tmp_path: Path) -> None:
    _seed_store(tmp_path)
    result = get_semantic_graph_data(str(tmp_path), scope="all", limit=20, min_share=1)
    assert result["success"] is True
    names = {n["name"] for n in result["nodes"]}
    assert {"BM25", "LangChain", "混合检索"} <= names
    assert result["meta"]["object_count"] == 3
    kinds = {n["kind"] for n in result["nodes"]}
    assert kinds == {"entity", "concept"}
    # entity-1 ↔ entity-2 共现边（共享 block-1，weight=1 >= min_share=1）
    edges = result["edges"]
    assert len(edges) == 1
    assert edges[0]["weight"] == 1


def test_relation_edges_filtered_by_min_share(tmp_path: Path) -> None:
    _seed_store(tmp_path)
    # min_share=2：唯一共现对只共享 1 个块，边被过滤
    result = get_semantic_graph_data(str(tmp_path), scope="all", limit=20, min_share=2)
    assert result["success"] is True
    assert result["edges"] == []


def test_topic_scope_filters_by_topic_prefix(tmp_path: Path) -> None:
    _seed_store(tmp_path)
    result = get_semantic_graph_data(str(tmp_path), scope="topic", filter_path="AI", limit=20)
    assert result["success"] is True
    # AI > RAG 主题下的文档提及 entity-1/entity-2/concept-1，不含 doc-3 的孤立实体
    names = {n["name"] for n in result["nodes"]}
    assert names == {"BM25", "LangChain", "混合检索"}
    assert "孤立实体" not in names


def test_doc_scope_with_doc_nodes(tmp_path: Path) -> None:
    _seed_store(tmp_path)
    result = get_semantic_graph_data(
        str(tmp_path), scope="doc", filter_path="Notes/AI/RAG.md", limit=20, include_docs=True
    )
    assert result["success"] is True
    doc_nodes = [n for n in result["nodes"] if n["kind"] == "doc"]
    assert len(doc_nodes) == 1
    assert doc_nodes[0]["path"] == "Notes/AI/RAG.md"
    doc_edges = [e for e in result["edges"] if e["relation_type"] == "MENTIONED_IN"]
    assert len(doc_edges) >= 1
    # 文档节点 id 与边 target 一致
    doc_ids = {n["id"] for n in doc_nodes}
    for edge in doc_edges:
        assert edge["target"] in doc_ids


def test_no_workspace_and_empty_store(tmp_path: Path) -> None:
    result = get_semantic_graph_data(None)
    assert result["success"] is False
    empty = get_semantic_graph_data(str(tmp_path))
    assert empty["success"] is False
    assert "未初始化" in empty["message"]


def test_inactive_objects_and_invalid_scope(tmp_path: Path) -> None:
    _seed_store(tmp_path)
    from sidecar.semantic.store import SemanticStore

    store = SemanticStore(tmp_path)
    with store.connect() as conn:
        conn.execute("UPDATE entities SET status='deleted' WHERE id='entity-1'")
    result = get_semantic_graph_data(str(tmp_path), scope="weird", limit=20)
    assert result["success"] is True
    # 非法 scope 回落 all；已失效实体不出现
    names = {n["name"] for n in result["nodes"]}
    assert "BM25" not in names
    assert result["meta"]["scope"] == "all"
