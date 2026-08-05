from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol

from config import config
from utils.text_utils import parse_frontmatter
from utils.topic_assigner import sync_wiki_with_files
from utils.topic_manager import TopicManager
from utils.topic_pending import load_pending


class _TopicsHost(Protocol):
    def _resolve_path(self, path: str) -> str | None: ...

    def _require_workspace(self, extra: dict | None = None, message: str = "") -> tuple[str | None, dict | None]: ...

    def _get_topic_tree_3tier(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def _set_abstract_config(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def _get_graph_data(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def _delete_topic_safe(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def _toggle_survey(self, params: dict[str, Any]) -> dict[str, Any]: ...


def _graph_topic_node_id(workspace: str, topic: dict, parent_tid: str | None = None) -> str:
    """Stable unique graph node id (name alone collides across L1/L2)."""
    path = topic.get("path")
    if path and workspace:
        try:
            rel = Path(path).relative_to(Path(workspace)).as_posix()
            return f"t:{rel}"
        except ValueError:
            pass
    name = topic.get("name", "")
    level = topic.get("level", 0)
    if level == 1:
        return f"t:L1:{name}"
    if parent_tid:
        return f"{parent_tid}/{name}"
    return f"t:{name}:L{level}"


class Topics3TierMixin:
    """三层主题系统扩展方法（通过 mixin 注入 TopicsHandler）"""

    _toggle_survey: Callable[[dict[str, Any]], dict[str, Any]]
    _delete_topic: Callable[[dict[str, Any]], dict[str, Any]]

    def _get_topic_tree_3tier(self, _params):
        """返回三层主题树（含文件系统扫描 + WIKI.md 解析 + 综述状态）"""
        workspace = config.workspace_path
        if not workspace:
            return {"success": True, "topics": [], "pending": []}

        with suppress(Exception):
            sync_wiki_with_files()

        tree = TopicManager.build_tree_from_filesystem(workspace)

        # 检查 Abstract 文件夹中的综述文件（方案四）
        abstract_folder = Path(workspace) / config.ABSTRACT_FOLDER
        if abstract_folder.exists():
            for l1 in tree:
                # 检查一级主题综述
                l1_abstract = abstract_folder / f"{l1['name']}.md"
                if l1_abstract.exists():
                    l1["has_abstract"] = True
                    l1["abstract_file"] = f"{config.ABSTRACT_FOLDER}/{l1['name']}.md"

                # 检查二级主题综述
                for l2 in l1.get("children", []):
                    l2_abstract = abstract_folder / l1["name"] / f"{l2['name']}.md"
                    if l2_abstract.exists():
                        l2["has_abstract"] = True
                        l2["abstract_file"] = f"{config.ABSTRACT_FOLDER}/{l1['name']}/{l2['name']}.md"

        pending = []
        with suppress(Exception):
            pending = load_pending()

        return {
            "success": True,
            "topics": TopicManager.tree_to_json(tree),
            "pending": pending,
        }

    def _set_abstract_config(self: _TopicsHost, params):
        """设置综述开关（仅二级主题可用）"""
        topic_name = params.get("topic_name", "").strip()
        level = params.get("level", 1)
        enable = params.get("enable", False)

        if not topic_name:
            return {"success": False, "message": "未指定主题"}

        if level == 1:
            return {"success": False, "message": "一级主题是组织容器，请给二级主题开启综述"}

        if enable:
            tree_result = self._get_topic_tree_3tier({})
            tree = tree_result.get("topics", [])
            can, reason = TopicManager.can_generate_abstract(topic_name, tree, level=level)
            if not can:
                return {"success": False, "message": reason}

        workspace, err = self._require_workspace()
        if err:
            return err

        result = self._toggle_survey({"topic": topic_name})
        if not result.get("success"):
            return result

        return {"success": True, "message": f"综述已{'开启' if enable else '关闭'}: {topic_name}"}

    def _append_topic_graph_nodes(self, topics, nodes, edges, seen_ids):
        workspace = config.workspace_path or ""

        def add_topic_nodes(topic, parent=None):
            tid = _graph_topic_node_id(workspace, topic, parent)
            if tid in seen_ids:
                return
            seen_ids.add(tid)
            nodes.append(
                {
                    "id": tid,
                    "name": topic["name"],
                    "level": topic["level"],
                    "type": "topic",
                    "has_abstract": topic.get("has_abstract", False),
                    "abstract_file": topic.get("abstract_file"),
                    "file_count": topic.get("file_count", 0),
                    "is_center": topic["level"] == 1,
                }
            )
            if parent:
                edges.append({"source": parent, "target": tid})

            children = topic.get("children", [])
            for child in children:
                add_topic_nodes(child, tid)

            topic_path = topic.get("path")
            if not topic_path or not Path(topic_path).is_dir():
                return
            for file_path in sorted(Path(topic_path).iterdir()):
                if not file_path.is_file() or file_path.name.startswith("."):
                    continue
                if file_path.name in ("综述.md", "WIKI.md", "tags.md"):
                    continue
                fid = f"file:{tid}:{file_path.stem}"
                if fid in seen_ids:
                    continue
                seen_ids.add(fid)
                nodes.append({"id": fid, "name": file_path.stem, "type": "file", "full_path": str(file_path)})
                edges.append({"source": tid, "target": fid})

        for topic in topics:
            add_topic_nodes(topic)

    def _collect_tag_files(self, workspace: str):
        ignored_dirs = {"_assets", "_templates", ".git", "__pycache__", "node_modules", ".venv", ".obsidian", ".trash"}
        tag_files: dict[str, list[str]] = {}
        ws_path = Path(workspace)

        def scan(path: Path):
            try:
                entries = sorted(path.iterdir(), key=lambda e: e.name.lower())
            except PermissionError:
                return
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    if entry.name not in ignored_dirs:
                        scan(entry)
                    continue
                if entry.suffix.lower() != ".md":
                    continue
                try:
                    text = entry.read_text(encoding="utf-8")
                    meta, _body = parse_frontmatter(text)
                except Exception:
                    continue
                if meta is None:
                    continue
                tags = meta.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                elif not isinstance(tags, list):
                    continue
                rel = str(entry.relative_to(ws_path))
                for raw_tag in tags:
                    tag = str(raw_tag).strip()
                    if tag:
                        tag_files.setdefault(tag, []).append(rel)

        scan(ws_path)
        return tag_files

    def _append_tag_graph_nodes(self, tag_files, workspace: str, nodes, edges, seen_ids):
        ws_path = Path(workspace)
        for tag_name, files in tag_files.items():
            tag_id = f"tag:{tag_name}"
            if tag_id not in seen_ids:
                seen_ids.add(tag_id)
                nodes.append({"id": tag_id, "name": tag_name, "type": "tag", "file_count": len(files)})
            for fpath in files:
                fid = f"file:{fpath}"
                if fid not in seen_ids:
                    seen_ids.add(fid)
                    nodes.append(
                        {"id": fid, "name": Path(fpath).stem, "type": "file", "full_path": str(ws_path / fpath)}
                    )
                edges.append({"source": tag_id, "target": fid})

    def _get_graph_data(self, params):
        """获取知识图谱数据，支持 filter: topic | tag | all"""
        filter_mode = params.get("filter", "topic")

        workspace = config.workspace_path
        if not workspace:
            return {"success": True, "nodes": [], "edges": [], "layout": "force"}

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        if filter_mode in ("topic", "all"):
            tree_result = self._get_topic_tree_3tier({})
            topics = tree_result.get("topics", [])
            self._append_topic_graph_nodes(topics, nodes, edges, seen_ids)

        if filter_mode in ("tag", "all"):
            self._append_tag_graph_nodes(self._collect_tag_files(workspace), workspace, nodes, edges, seen_ids)

        return {
            "success": True,
            "nodes": nodes,
            "edges": edges,
            "layout": "force",
        }

    def _delete_topic_safe(self, params):
        """安全删除主题（含删除保护）"""
        topic_name = params.get("topic_name", "").strip()

        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}

        tree_result = self._get_topic_tree_3tier({})
        tree = tree_result.get("topics", [])
        topic_level = 0
        for l1 in tree:
            if l1["name"] == topic_name:
                topic_level = 1
                break
            for l2 in l1.get("children", []):
                if l2["name"] == topic_name:
                    topic_level = 2
                    break
                for l3 in l2.get("children", []):
                    if l3["name"] == topic_name:
                        topic_level = 3
                        break
        if topic_level > 0:
            can, reason = TopicManager.can_delete_topic(topic_name, topic_level, tree)
            if not can:
                return {"success": False, "message": reason}

        return self._delete_topic(params)

    def register_routes_3tier(self: _TopicsHost, router):
        """注册三层主题相关路由"""
        router.register("get_topic_tree_3tier", self._get_topic_tree_3tier)
        router.register("set_abstract_config", self._set_abstract_config)
        router.register("get_graph_data", self._get_graph_data)
        router.register("delete_topic_safe", self._delete_topic_safe)
