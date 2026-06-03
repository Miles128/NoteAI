from pathlib import Path

from sidecar.mixins.topics_3tier_mixin import _graph_topic_node_id


def test_graph_topic_node_id_unique_when_names_collide() -> None:
    workspace = "/workspace"
    l1 = {
        "name": "产品应用",
        "level": 1,
        "path": str(Path(workspace) / "Notes" / "产品应用"),
    }
    l2 = {
        "name": "产品应用",
        "level": 2,
        "path": str(Path(workspace) / "Notes" / "AI" / "产品应用"),
    }
    l1_id = _graph_topic_node_id(workspace, l1)
    l2_id = _graph_topic_node_id(workspace, l2, l1_id)
    assert l1_id != l2_id
    assert l1_id == "t:Notes/产品应用"
    assert l2_id == "t:Notes/AI/产品应用"
