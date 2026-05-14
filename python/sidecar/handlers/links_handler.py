import re
import sys
import threading
from pathlib import Path

from config import config, is_ignored_dir
from sidecar.handlers.base import BaseHandler
from utils.link_indexer import discover_links, get_backlinks, confirm_link, reject_link, confirm_all_links


class LinksHandler(BaseHandler):
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
            finally:
                self._link_discovery_lock.release()

            self._send_response({
                "id": "event",
                "result": {
                    "type": "link_discovery_complete",
                    "data": result,
                }
            })

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

        # Quick auto-assign for untopiced files before building graph
        try:
            from utils.topic_assigner import auto_assign_topic_for_file
            quick_count = 0
            for f in workspace_path.rglob('*.md'):
                if f.name.startswith('.') or 'wiki' in f.parts: continue
                try:
                    t = f.read_text(encoding='utf-8')
                    fm, _ = self._parse_frontmatter(t)
                    if not fm or not fm.get('topic'):
                        r = auto_assign_topic_for_file(str(f), use_llm=False)
                        if r and r.get('status') == 'auto_assigned':
                            quick_count += 1
                except Exception: pass
            if quick_count > 0:
                sys.stderr.write(f"[links] quick auto_assign: {quick_count} files\n")
                sys.stderr.flush()
        except Exception: pass

        file_data = []
        for md_file in workspace_path.rglob('*.md'):
            total_md += 1
            if md_file.name.startswith('.') or 'wiki' in md_file.parts:
                skipped_name += 1
                continue
            if md_file.name.lower() in ('wiki.md', 'tags.md'):
                skipped_name += 1
                continue
            if any(is_ignored_dir(p.name) for p in md_file.relative_to(workspace_path).parents):
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
                is_survey = md_file.name.endswith('_综述.md') or md_file.name.endswith('综述.md')

                # Extract topic & tags from parsed YAML, with regex fallback for damaged YAML
                topic = None
                file_tags = []

                if meta is not None and isinstance(meta, dict) and meta:
                    topic = meta.get('topic')
                    if isinstance(topic, str):
                        topic = topic.strip().strip("'\"")
                    elif isinstance(topic, list) and topic:
                        topic = str(topic[0]).strip().strip("'\"")
                    file_tags = meta.get('tags', [])
                    if isinstance(file_tags, str):
                        tags = [t.strip() for t in file_tags.split(',') if t.strip()]
                    elif isinstance(file_tags, list):
                        tags = [str(t).strip() for t in file_tags if str(t).strip()]

                # Fallback: regex extraction for damaged YAML that yaml.safe_load couldn't parse
                if not topic or (not tags and not file_tags):
                    try:
                        yaml_raw = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('﻿'))
                        if yaml_raw:
                            for line in yaml_raw.group(1).split('\n'):
                                idx = line.find(':')
                                if idx < 0: continue
                                key = line[:idx].strip()
                                val = line[idx+1:].strip().strip("'\"")
                                if key == 'topic' and val and not topic:
                                    topic = val
                                elif key == 'topics' and val and not topic:
                                    if val.startswith('['):
                                        items = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
                                        if items: topic = items[0]
                                elif key == 'tags' and val and (not tags):
                                    if val.startswith('['):
                                        tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
                    except Exception:
                        pass

                if meta is None:
                    body = text
                    skipped_no_yaml += 1

                if is_survey and not topic:
                    topic = re.sub(r'[_\s]*综述$', '', file_name).strip()

                file_data.append({
                    "rel_path": rel_path,
                    "file_name": file_name,
                    "topic": topic,
                    "tags": tags,
                    "body": body,
                    "is_survey": is_survey,
                })
            except Exception as e:
                error_count += 1
                if not first_error:
                    first_error = f"{md_file.name}: {type(e).__name__}: {e}"

        all_file_ids = set()
        for fd in file_data:
            all_file_ids.add(fd["rel_path"])

        for fd in file_data:
            rel_path = fd["rel_path"]
            file_name = fd["file_name"]
            topic = fd["topic"]
            tags = fd["tags"]
            body = fd["body"]
            is_survey = fd["is_survey"]

            if is_survey:
                if topic:
                    edges.append({
                        "source": rel_path,
                        "target": "topic:" + topic,
                        "type": "topic"
                    })
                nodes[rel_path] = {
                    "id": rel_path,
                    "label": file_name,
                    "topic": topic,
                    "tags": tags,
                    "is_survey": True,
                }
            else:
                nodes[rel_path] = {
                    "id": rel_path,
                    "label": file_name,
                    "topic": topic,
                    "tags": tags,
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
                for other_fd in file_data:
                    if Path(other_fd["rel_path"]).stem == target_name:
                        if other_fd["rel_path"] != rel_path:
                            edges.append({
                                "source": rel_path,
                                "target": other_fd["rel_path"],
                                "type": "link"
                            })
                        break

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
            node = {
                "id": n["id"],
                "label": n["label"],
                "nodeType": "file",
                "topic": n.get("topic"),
                "tags": n.get("tags", []),
            }
            if n.get("is_survey"):
                node["is_survey"] = True
            all_nodes.append(node)
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

    def register_routes(self, router):
        router.register("discover_links", self._discover_links)
        router.register("get_backlinks", self._get_backlinks)
        router.register("get_relation_graph", self._get_relation_graph)
        router.register("confirm_link", self._confirm_link)
        router.register("reject_link", self._reject_link)
        router.register("confirm_all_links", self._confirm_all_links)