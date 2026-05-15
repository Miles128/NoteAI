"""主题管理 — 三层主题树 + 综述控制 + 删除保护
替换 python/sidecar/mixins/topics_mixin.py
"""

import logging
import shutil
from pathlib import Path

import yaml

from config import config, is_ignored_dir
from utils.topic_manager import (
    LEVEL1_TOPICS,
    TopicManager,
)

logger = logging.getLogger(__name__)

# handler_map 中此 mixin 对应的方法名常量（供 server.py 注册和测试验证）
TOPIC_METHODS = {
    "get_topic_tree": "_get_topic_tree",
    "get_topic_files": "_get_topic_files",
    "assign_topic_to_file": "_assign_topic_to_file",
    "batch_assign_topics": "_batch_assign_topics",
    "move_topic_folder": "_move_topic_folder",
    "delete_topic": "_delete_topic",
    "create_topic_folder": "_create_topic_folder",
    "set_abstract_config": "_set_abstract_config",
    "generate_abstract": "_generate_abstract",
    "get_graph_data": "_get_graph_data",
    "get_pending_topics": "_get_pending_topics",
}


class TopicsMixin:
    """三层主题管理 mixin"""

    # ================================================================
    # 主题树
    # ================================================================

    def _get_topic_tree(self, params):
        workspace = config.workspace_path
        if not workspace:
            return {"topics": [], "pending": []}

        tree = self._build_tree_from_filesystem(workspace)

        # 检查 Abstract 文件夹中的综述文件
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

        pending = self._load_pending_topics()
        return {
            "topics": TopicManager.tree_to_json(tree),
            "pending": pending,
        }

    def _build_tree_from_filesystem(self, workspace):
        tree = {}
        notes_dir = Path(workspace) / "Notes"
        if not notes_dir.exists():
            return []

        for l1_dir in sorted(notes_dir.iterdir()):
            if not l1_dir.is_dir() or l1_dir.name.startswith("."):
                continue
            if is_ignored_dir(l1_dir):
                continue
            if l1_dir.name not in LEVEL1_TOPICS:
                continue

            abs_path = str(l1_dir)
            tree[l1_dir.name] = {
                "name": l1_dir.name, "level": 1, "parent": None,
                "children": {}, "path": abs_path,
                "has_abstract": (l1_dir / "综述.md").exists(),
                "abstract_file": str(l1_dir / "综述.md") if (l1_dir / "综述.md").exists() else None,
                "file_count": 0,
            }

            for l2_dir in sorted(l1_dir.iterdir()):
                if not l2_dir.is_dir() or l2_dir.name.startswith("."):
                    continue
                abs_path2 = str(l2_dir)
                tree[l1_dir.name]["children"][l2_dir.name] = {
                    "name": l2_dir.name, "level": 2, "parent": l1_dir.name,
                    "children": {}, "path": abs_path2,
                    "has_abstract": (l2_dir / "综述.md").exists(),
                    "abstract_file": str(l2_dir / "综述.md") if (l2_dir / "综述.md").exists() else None,
                    "file_count": 0,
                }

                for l3_dir in sorted(l2_dir.iterdir()):
                    if not l3_dir.is_dir() or l3_dir.name.startswith("."):
                        continue
                    tree[l1_dir.name]["children"][l2_dir.name]["children"][l3_dir.name] = {
                        "name": l3_dir.name, "level": 3, "parent": l2_dir.name,
                        "children": {}, "path": str(l3_dir), "file_count": 0,
                    }

        # Build tree from flat entries
        entries = []
        for l1_name, l1 in tree.items():
            entries.append({"name": l1_name, "level": 1, "parent": None})
            for l2_name in l1["children"]:
                entries.append({"name": l2_name, "level": 2, "parent": l1_name})
                for l3_name in l1["children"][l2_name]["children"]:
                    entries.append({"name": l3_name, "level": 3, "parent": l2_name})

        result = TopicManager.build_topic_tree(entries)

        # Merge file counts and abstract status from filesystem
        for l1 in result:
            l1_fs = tree.get(l1["name"])
            if l1_fs:
                l1["path"] = l1_fs["path"]
                l1["has_abstract"] = l1_fs["has_abstract"]
                l1["abstract_file"] = l1_fs["abstract_file"]
                l1["file_count"] = self._count_files(l1["path"], exclude_abstract=True)
            for l2 in l1.get("children", []):
                l2_fs = tree.get(l1["name"], {}).get("children", {}).get(l2["name"])
                if l2_fs:
                    l2["path"] = l2_fs["path"]
                    l2["has_abstract"] = l2_fs["has_abstract"]
                    l2["abstract_file"] = l2_fs["abstract_file"]
                    l2["file_count"] = self._count_files(l2["path"], exclude_abstract=True)
                for l3 in l2.get("children", []):
                    if l1.get("name") in tree and l2["name"] in tree[l1["name"]]["children"]:
                        l3_fs = tree[l1["name"]]["children"][l2["name"]]["children"].get(l3["name"])
                        if l3_fs:
                            l3["path"] = l3_fs["path"]
                            l3["file_count"] = self._count_files(l3["path"])

        return result

    def _count_files(self, path: str | None, exclude_abstract=False) -> int:
        if not path:
            return 0
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return 0
        count = 0
        for f in p.iterdir():
            if f.is_file() and not f.name.startswith("."):
                if exclude_abstract and f.name == "综述.md":
                    continue
                count += 1
        return count

    # ================================================================
    # 文件列表
    # ================================================================

    def _get_topic_files(self, params):
        topic_name = params.get("topic_name", "")
        level = params.get("level", 1)

        workspace = config.workspace_path
        if not workspace:
            return {"files": [], "error": "工作区未设置"}

        topic_path = self._find_topic_path(topic_name, level, workspace)
        if not topic_path:
            return {"files": [], "error": f"找不到「{topic_name}」"}

        files = []
        p = Path(topic_path)
        if p.exists():
            for f in p.glob("**/*.md"):
                if f.is_file() and not f.name.startswith("."):
                    files.append({
                        "path": str(f.relative_to(Path(workspace))),
                        "name": f.stem,
                    })
        return {"files": sorted(files, key=lambda x: x["name"])}

    def _find_topic_path(self, name, level, workspace):
        if level == 1:
            p = Path(workspace) / "Notes" / name
            return str(p) if p.exists() else None
        if level == 2:
            notes = Path(workspace) / "Notes"
            for d in notes.iterdir():
                if d.is_dir():
                    p = d / name
                    if p.exists():
                        return str(p)
        elif level == 3:
            notes = Path(workspace) / "Notes"
            for d1 in notes.iterdir():
                if d1.is_dir():
                    for d2 in d1.iterdir():
                        if d2.is_dir():
                            p = d2 / name
                            if p.exists():
                                return str(p)
        return None

    # ================================================================
    # 主题分配
    # ================================================================

    def _assign_topic_to_file(self, params):
        file_path = params.get("file_path", "")
        topics = params.get("topics", [])

        resolved = self._resolve_path(file_path)
        if not resolved:
            return {"success": False, "message": f"路径无效: {file_path}"}

        p = Path(resolved)
        if not p.exists():
            return {"success": False, "message": f"文件不存在: {file_path}"}

        try:
            content = p.read_text(encoding="utf-8")
            fm, body = self._parse_frontmatter(content)
            fm["topic"] = self._build_topic_list(topics)
            new_content = self._dump_frontmatter(fm, body)
            p.write_text(new_content, encoding="utf-8")
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _batch_assign_topics(self, params):
        files = params.get("files", [])
        topics = params.get("topics", [])
        results = []
        for fp in files:
            r = self._assign_topic_to_file({"file_path": fp, "topics": topics})
            results.append({"file": fp, "success": r.get("success")})
        return {"results": results}

    def _build_topic_list(self, topics):
        """构造 YAML 三层嵌套列表"""
        l1 = next((t["name"] for t in topics if t["level"] == 1), None)
        l2 = next((t["name"] for t in topics if t["level"] == 2), None)
        l3 = next((t["name"] for t in topics if t["level"] == 3), None)

        if l3 and l2:
            return [l1, {l2: [l3]}] if l1 else [{l2: [l3]}]
        if l2:
            return [l1, l2] if l1 else [l2]
        if l1:
            return [l1]
        return []

    def _dump_frontmatter(self, fm, body):
        yaml_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()
        return f"---\n{yaml_str}\n---\n\n{body.strip()}"

    # ================================================================
    # 文件夹操作
    # ================================================================

    def _create_topic_folder(self, params):
        folder_name = params.get("name", "").strip()
        parent_path = params.get("parent_path", "")

        if not folder_name:
            return {"success": False, "message": "名称不能为空"}
        if "/" in folder_name or ".." in folder_name:
            return {"success": False, "message": "名称含非法字符"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "工作区未设置"}

        if parent_path:
            resolved = self._resolve_path(parent_path)
            if not resolved:
                return {"success": False, "message": "父路径无效"}
            parent = Path(resolved)
        else:
            parent = Path(workspace) / "Notes"

        level = TopicManager.determine_folder_level(str(parent), workspace)
        if level == 1 and folder_name not in LEVEL1_TOPICS:
            return {"success": False, "message": f"一级必须是: {', '.join(LEVEL1_TOPICS)}"}

        new_path = parent / folder_name
        if new_path.exists():
            return {"success": False, "message": "已存在同名文件夹"}

        new_path.mkdir(parents=True)
        label = f"L{level}" if level > 0 else "普通文件夹"
        return {"success": True, "message": f"已创建 {label}: {folder_name}",
                "path": str(new_path.relative_to(Path(workspace))), "level": level if level > 0 else None}

    def _delete_topic(self, params):
        topic_name = params.get("topic_name", "")
        level = params.get("level", 2)

        if level == 1 and topic_name in LEVEL1_TOPICS:
            return {"success": False, "message": "预定义一级不可删除"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "工作区未设置"}

        tree = TopicManager.build_topic_tree(
            self._get_topic_tree({}).get("topics", [])
        )
        can, reason = TopicManager.can_delete_topic(topic_name, level, tree)
        if not can:
            return {"success": False, "message": reason}

        tp = self._find_topic_path(topic_name, level, workspace)
        if not tp:
            return {"success": False, "message": f"找不到: {topic_name}"}

        shutil.rmtree(tp)
        return {"success": True, "message": f"已删除: {topic_name}" + (f". {reason}" if reason else "")}

    def _move_topic_folder(self, params):
        topic_name = params.get("topic_name", "")
        level = params.get("level", 2)
        new_parent = params.get("new_parent", "")

        workspace = config.workspace_path
        src = self._find_topic_path(topic_name, level, workspace)
        if not src:
            return {"success": False, "message": f"找不到: {topic_name}"}

        dest_parent = self._find_topic_path(new_parent, level - 1, workspace)
        if not dest_parent:
            return {"success": False, "message": f"目标不存在: {new_parent}"}

        dest = Path(dest_parent) / Path(src).name
        if dest.exists():
            return {"success": False, "message": "目标已存在"}

        shutil.move(src, str(dest))
        return {"success": True}

    # ================================================================
    # 综述
    # ================================================================

    def _set_abstract_config(self, params):
        topic_name = params.get("topic_name", "")
        level = params.get("level", 1)
        enable = params.get("enable", False)

        if enable:
            tree = TopicManager.build_topic_tree(
                self._get_topic_tree({}).get("topics", [])
            )
            can, reason = TopicManager.can_generate_abstract(topic_name, tree, level=level)
            if not can:
                return {"success": False, "message": reason}

        workspace = config.workspace_path
        tp = self._find_topic_path(topic_name, level, workspace)
        if not tp:
            return {"success": False, "message": f"找不到: {topic_name}"}

        af = Path(tp) / "综述.md"
        if enable:
            af.write_text(f"# {topic_name} 综述\n\n> 自动生成中...\n", encoding="utf-8")
        elif af.exists():
            af.unlink()
        return {"success": True}

    def _generate_abstract(self, params):
        topic_name = params.get("topic_name", "")
        level = params.get("level", 1)

        workspace = config.workspace_path
        tp = self._find_topic_path(topic_name, level, workspace)
        if not tp:
            return {"success": False, "message": f"找不到: {topic_name}"}

        try:
            from modules.abstract_generator import AbstractGenerator
            gen = AbstractGenerator()
            return gen.generate(topic_name, tp, level, workspace)
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ================================================================
    # 知识图谱
    # ================================================================

    def _get_graph_data(self, params):
        tree_result = self._get_topic_tree({})
        tree = tree_result.get("topics", [])

        nodes = []
        edges = []

        def add(topic, parent=None):
            nodes.append({
                "id": topic["name"], "name": topic["name"],
                "level": topic["level"],
                "has_abstract": topic.get("has_abstract", False),
                "abstract_file": topic.get("abstract_file"),
                "file_count": topic.get("file_count", 0),
                "is_center": topic["level"] == 1,
            })
            if parent:
                edges.append({"source": parent, "target": topic["name"]})
            for child in topic.get("children", []):
                add(child, topic["name"])

        for l1 in tree:
            add(l1)

        return {"nodes": nodes, "edges": edges, "layout": "three_tier_radial"}

    # ================================================================
    # 自动分配（AI）
    # ================================================================

    def _get_pending_topics(self, params):
        """获取待确认主题列表"""
        return {"pending": self._load_pending_topics()}

    def _auto_assign_topic(self, params):
        file_path = params.get("file_path", "")
        resolved = self._resolve_path(file_path)
        if not resolved:
            return {"success": False, "message": "路径无效"}
        # 加入待确认列表
        pending = self._load_pending_topics()
        pending.append({"file": file_path, "status": "pending"})
        self._save_pending_topics(pending)
        return {"success": True, "pending": True}
