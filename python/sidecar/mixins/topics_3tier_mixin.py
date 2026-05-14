from pathlib import Path

from config import config


class Topics3TierMixin:
    """三层主题系统扩展方法（通过 mixin 注入 TopicsHandler）"""

    def _get_topic_tree_3tier(self, params):
        """返回三层主题树（含文件系统扫描 + WIKI.md 解析 + 综述状态）"""
        from utils.topic_manager import TopicManager, LEVEL1_TOPICS
        workspace = config.workspace_path
        if not workspace:
            return {"success": True, "topics": [], "pending": []}

        tree = TopicManager.build_tree_from_filesystem(workspace)

        wiki_entries = self._parse_wiki_headings()
        for entry in wiki_entries:
            name = entry["name"]
            level = entry["level"]
            for l1 in tree:
                if l1["name"] == name and level == 2:
                    l1["has_abstract"] = True
                for l2 in l1.get("children", []):
                    if l2["name"] == name and level == 3:
                        l2["has_abstract"] = True

        pending = []
        try:
            from utils.topic_assigner import load_pending
            pending = load_pending()
        except Exception:
            pass

        return {
            "success": True,
            "topics": TopicManager.tree_to_json(tree),
            "pending": pending,
        }

    def _create_topic_folder(self, params):
        """创建新主题文件夹（自动判定一二三级）"""
        from utils.topic_manager import TopicManager, LEVEL1_TOPICS
        folder_name = params.get("name", "").strip()
        parent_path = params.get("parent_path", "")
        level_hint = params.get("level", 0)

        if not folder_name:
            return {"success": False, "message": "名称不能为空"}
        if "/" in folder_name or ".." in folder_name:
            return {"success": False, "message": "名称含非法字符"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        if parent_path:
            parent = Path(self._resolve_path(parent_path) or "")
        else:
            parent = Path(workspace) / config.NOTES_FOLDER

        if not parent.exists():
            return {"success": False, "message": "父目录不存在"}

        if level_hint == 0:
            level = TopicManager.determine_folder_level(str(parent), workspace)
        else:
            level = level_hint

        if level == 1 and folder_name not in LEVEL1_TOPICS:
            return {
                "success": False,
                "message": f"一级标题必须是预定义的: {', '.join(LEVEL1_TOPICS)}",
            }

        new_path = parent / folder_name
        if new_path.exists():
            return {"success": False, "message": "已存在同名文件夹"}

        new_path.mkdir(parents=True)
        topic_label = f"L{level}" if 1 <= level <= 3 else "普通文件夹"
        return {
            "success": True,
            "message": f"已创建 {topic_label}: {folder_name}",
            "topic": str(new_path.relative_to(Path(workspace))),
            "level": level if 1 <= level <= 3 else None,
        }

    def _set_abstract_config(self, params):
        """设置综述开关（仅二级主题可用）"""
        from utils.topic_manager import TopicManager
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

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        result = self._toggle_survey({"topic": topic_name})
        if not result.get("success"):
            return result

        return {"success": True, "message": f"综述已{'开启' if enable else '关闭'}: {topic_name}"}

    def _get_graph_data(self, params):
        """获取知识图谱数据，支持 filter: topic | tag | all"""
        from pathlib import Path
        filter_mode = params.get("filter", "topic")

        workspace = config.workspace_path
        if not workspace:
            return {"success": True, "nodes": [], "edges": [], "layout": "force"}

        nodes = []
        edges = []
        seen_ids = set()

        if filter_mode in ("topic", "all"):
            tree_result = self._get_topic_tree_3tier({})
            topics = tree_result.get("topics", [])

            def add_topic_nodes(topic, parent=None):
                tid = topic["name"]
                if tid in seen_ids:
                    return
                seen_ids.add(tid)
                nodes.append({
                    "id": tid, "name": tid,
                    "level": topic["level"], "type": "topic",
                    "has_abstract": topic.get("has_abstract", False),
                    "abstract_file": topic.get("abstract_file"),
                    "file_count": topic.get("file_count", 0),
                    "is_center": topic["level"] == 1,
                })
                if parent:
                    edges.append({"source": parent, "target": tid})

                children = topic.get("children", [])
                if children:
                    for child in children:
                        add_topic_nodes(child, tid)
                else:
                    topic_path = topic.get("path")
                    if topic_path and Path(topic_path).is_dir():
                        for f in sorted(Path(topic_path).iterdir()):
                            if not f.is_file() or f.name.startswith("."):
                                continue
                            if f.name in ("综述.md", "WIKI.md", "tags.md"):
                                continue
                            fid = f"file:{tid}:{f.stem}"
                            if fid in seen_ids:
                                continue
                            seen_ids.add(fid)
                            nodes.append({
                                "id": fid, "name": f.stem,
                                "type": "file", "full_path": str(f),
                            })
                            edges.append({"source": tid, "target": fid})

            for l1 in topics:
                add_topic_nodes(l1)

        if filter_mode in ("tag", "all"):
            tag_files = {}
            ws_path = Path(workspace)

            def _scan_tags(path):
                p = Path(path) if not isinstance(path, Path) else path
                try:
                    for entry in sorted(p.iterdir(), key=lambda e: e.name.lower()):
                        if entry.name.startswith("."):
                            continue
                        if entry.is_dir():
                            if entry.name in ("_assets", "_templates", ".git", "__pycache__", "node_modules", ".venv", ".obsidian", ".trash"):
                                continue
                            _scan_tags(entry)
                        elif entry.suffix.lower() == ".md":
                            try:
                                text = entry.read_text(encoding="utf-8")
                                meta, _body = self._parse_frontmatter(text)
                                if meta is None:
                                    continue
                                tags = meta.get("tags", [])
                                if isinstance(tags, str):
                                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                                elif not isinstance(tags, list):
                                    continue
                                rel = str(entry.relative_to(ws_path))
                                for tag in tags:
                                    tag = str(tag).strip()
                                    if tag:
                                        if tag not in tag_files:
                                            tag_files[tag] = []
                                        tag_files[tag].append(rel)
                            except Exception:
                                pass
                except PermissionError:
                    pass

            _scan_tags(ws_path)

            for tag_name, files in tag_files.items():
                tag_id = f"tag:{tag_name}"
                if tag_id not in seen_ids:
                    seen_ids.add(tag_id)
                    nodes.append({
                        "id": tag_id, "name": tag_name,
                        "type": "tag", "file_count": len(files),
                    })
                for fpath in files:
                    fid = f"file:{fpath}"
                    if fid not in seen_ids:
                        seen_ids.add(fid)
                        nodes.append({
                            "id": fid, "name": Path(fpath).stem,
                            "type": "file", "full_path": str(ws_path / fpath),
                        })
                    edges.append({"source": tag_id, "target": fid})

        return {
            "success": True,
            "nodes": nodes,
            "edges": edges,
            "layout": "force",
        }

    def _delete_topic_safe(self, params):
        """安全删除主题（含删除保护）"""
        from utils.topic_manager import TopicManager, LEVEL1_TOPICS
        topic_name = params.get("name", "").strip()

        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}

        if topic_name in LEVEL1_TOPICS:
            tree_result = self._get_topic_tree_3tier({})
            tree = tree_result.get("topics", [])
            can, reason = TopicManager.can_delete_topic(topic_name, 1, tree)
            if not can:
                return {"success": False, "message": reason}

        return self._delete_topic(params)

    def register_routes_3tier(self, router):
        """注册三层主题相关路由"""
        router.register("get_topic_tree_3tier", self._get_topic_tree_3tier)
        router.register("create_topic_folder", self._create_topic_folder)
        router.register("set_abstract_config", self._set_abstract_config)
        router.register("get_graph_data", self._get_graph_data)
        router.register("delete_topic_safe", self._delete_topic_safe)