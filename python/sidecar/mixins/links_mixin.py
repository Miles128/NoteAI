"""Link discovery, graph, backlink confirm (from python/main.py)."""

import json
import re
import sys
import shutil
import threading
from pathlib import Path

import yaml
from config import config, is_ignored_dir
from utils.link_indexer import discover_links, get_backlinks, confirm_link, reject_link, confirm_all_links

class LinksMixin:
    def _discover_links(self, params):
        if not self._link_discovery_lock.acquire(blocking=False):
            return {"success": False, "message": "链接发现正在进行中，请等待完成"}

        def run():
            def progress_callback(stage, total, message):
                self._send_progress("link-discovery-progress", int(stage / total * 100), message)

            try:
                result = discover_links(progress_callback=progress_callback)
            except Exception as e:
                result = {"success": False, "message": f"链接发现失败: {e}"}

            self._link_discovery_lock.release()
            self._send_response({
                "id": "event",
                "result": {
                    "type": "link_discovery_complete",
                    "data": result,
                }
            })

        import threading
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return {"success": True, "status": "started", "message": "链接发现已启动"}

    def _get_backlinks(self, params):
        file_path = params.get("file_path", "") or ""
        return get_backlinks(file_path)

    def _get_relation_graph(self, params):
        return self._cached_or_compute("relation_graph", self._compute_relation_graph)

    def _compute_relation_graph(self):
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        workspace_path = Path(workspace)
        nodes = {}
        edges = []
        skipped_no_yaml = 0
        skipped_name = 0
        total_md = 0
        first_file_debug = ""
        error_count = 0
        first_error = ""

        for md_file in workspace_path.rglob('*.md'):
            total_md += 1
            if md_file.name.startswith('.') or md_file.name.lower() in ('wiki.md', 'tags.md'):
                skipped_name += 1
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                if not first_file_debug:
                    first_file_debug = f"read_ok={md_file.name}, len={len(text)}"
                meta, body = self._parse_frontmatter(text)
                rel_path = str(md_file.relative_to(workspace_path))
                file_name = md_file.stem
                topic = None
                tags = []

                if meta is not None:
                    topic = meta.get('topic')
                    if isinstance(topic, str):
                        topic = topic.strip().strip("'\"")
                    tags = meta.get('tags', [])
                    if isinstance(tags, str):
                        tags = [t.strip().strip("'\"") for t in tags.split(',') if t.strip()]
                    elif not isinstance(tags, list):
                        tags = []
                else:
                    body = text
                    skipped_no_yaml += 1

                if not first_file_debug:
                    first_file_debug = f"file={md_file.name}, rel={rel_path}, topic={topic}"

                nodes[rel_path] = {
                    "id": rel_path,
                    "label": file_name,
                    "topic": topic,
                    "tags": tags
                }

                if topic:
                    edges.append({
                        "source": rel_path,
                        "target": "topic:" + topic,
                        "type": "topic"
                    })

                for tag in tags:
                    edges.append({
                        "source": rel_path,
                        "target": "tag:" + tag,
                        "type": "tag"
                    })

                link_pattern = re.compile(r'\[\[([^\]]+)\]\]')
                for match in link_pattern.finditer(body):
                    target_name = match.group(1).strip()
                    target_name = target_name.split('|')[0].strip()
                    target_name = target_name.split('#')[0].strip()
                    if not target_name:
                        continue
                    for other_rel, other_node in nodes.items():
                        if Path(other_rel).stem == target_name:
                            edges.append({
                                "source": rel_path,
                                "target": other_rel,
                                "type": "link"
                            })
                            break
            except Exception as e:
                error_count += 1
                if not first_error:
                    first_error = f"{md_file.name}: {type(e).__name__}: {e}"

        topic_nodes = {}
        tag_nodes = {}
        for edge in edges:
            if edge["type"] == "topic":
                t = edge["target"].replace("topic:", "", 1)
                if t not in topic_nodes:
                    topic_nodes[t] = {"id": "topic:" + t, "label": t, "nodeType": "topic"}
            elif edge["type"] == "tag":
                t = edge["target"].replace("tag:", "", 1)
                if t not in tag_nodes:
                    tag_nodes[t] = {"id": "tag:" + t, "label": t, "nodeType": "tag"}

        all_nodes = []
        for rel, n in nodes.items():
            all_nodes.append({
                "id": n["id"],
                "label": n["label"],
                "nodeType": "file",
                "topic": n.get("topic"),
                "tags": n.get("tags", [])
            })
        for n in topic_nodes.values():
            all_nodes.append(n)
        for n in tag_nodes.values():
            all_nodes.append(n)

        return {
            "success": True,
            "nodes": all_nodes,
            "edges": edges,
            "debug": {
                "workspace": workspace,
                "workspace_exists": workspace_path.exists(),
                "total_md": total_md,
                "skipped_name": skipped_name,
                "skipped_no_yaml": skipped_no_yaml,
                "nodes_with_yaml": len(nodes),
                "topic_nodes": len(topic_nodes),
                "tag_nodes": len(tag_nodes),
                "total_edges": len(edges),
                "first_file": first_file_debug,
                "error_count": error_count,
                "first_error": first_error
            }
        }

    def _confirm_link(self, params):
        from_path = params.get("from", "")
        to_path = params.get("to", "")
        if not from_path or not to_path:
            return {"success": False, "message": "参数不完整"}
        return confirm_link(from_path, to_path)

    def _reject_link(self, params):
        from_path = params.get("from", "")
        to_path = params.get("to", "")
        if not from_path or not to_path:
            return {"success": False, "message": "参数不完整"}
        return reject_link(from_path, to_path)

    def _confirm_all_links(self, params):
        return confirm_all_links()
