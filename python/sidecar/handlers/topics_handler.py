import re
import sys
from collections import Counter
from pathlib import Path

import yaml
from config import config, is_ignored_dir
from sidecar.handlers.base import BaseHandler
from sidecar.mixins.topics_3tier_mixin import Topics3TierMixin


class TopicsHandler(BaseHandler, Topics3TierMixin):
    def _get_topic_tree(self, params):
        return self._get_topic_tree_3tier(params)

    def _parse_wiki_headings(self):
        workspace = config.workspace_path
        if not workspace:
            return []
        wiki_path = Path(workspace) / "wiki" / "WIKI.md"
        if not wiki_path.exists():
            wiki_path = Path(workspace) / "WIKI.md"
        if not wiki_path.exists():
            return []
        try:
            text = wiki_path.read_text(encoding='utf-8')
            headings = []
            for line in text.split('\n'):
                stripped = line.rstrip()
                if stripped.startswith('## '):
                    name = stripped[3:].strip()
                    headings.append({"name": name, "level": 2})
                elif stripped.startswith('### '):
                    name = stripped[4:].strip()
                    headings.append({"name": name, "level": 3})
            return headings
        except Exception as e:
            sys.stderr.write(f"[topics_handler] reading wiki headings: {e}\n")
            sys.stderr.flush()
            return []

    def _auto_assign_topic(self, params):
        path = params.get("path", "")
        if not path:
            return {"success": False, "message": "未指定文件"}
        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)
        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}
        from utils.topic_assigner import auto_assign_topic_for_file, write_topic_to_file, move_file_to_notes_topic_folder
        try:
            result = auto_assign_topic_for_file(str(full_path))
            if not result:
                return {"success": False, "message": "未找到匹配主题"}
            if result.get("status") != "auto_assigned":
                return {"success": False, "message": "需要人工确认主题", "candidates": result.get("candidates", [])}
            topic = result.get("topic", "")
            if not topic:
                return {"success": False, "message": "未找到匹配主题"}
            write_topic_to_file(str(full_path), topic)
            try:
                move_file_to_notes_topic_folder(str(full_path), topic)
            except Exception as e:
                sys.stderr.write(f"[topics_handler] auto assign file move error: {e}\n")
            self._start_task(f"cascade_update_{topic}", self._do_cascade_survey_update, args=(topic,))
            return {"success": True, "topic": topic}
        except Exception as e:
            return {"success": False, "message": f"自动分配失败: {str(e)}"}

    def _batch_auto_assign_topics(self, params):
        if not config.workspace_path:
            return {"success": False, "message": "未设置工作区或工作区不存在"}
        from utils.topic_assigner import auto_assign_topic_for_file, write_topic_to_file, move_file_to_notes_topic_folder

        ws = Path(config.workspace_path)
        md_files = [f for f in ws.rglob("*.md") if not f.name.startswith(".")
                    and "wiki" not in f.parts and not is_ignored_dir(f.parent.name)]
        total = len(md_files)
        auto_assigned = 0
        need_confirm = 0
        skipped = 0
        assigned_topics = set()

        for i, md_file in enumerate(md_files):
            try:
                result = auto_assign_topic_for_file(str(md_file))
                if result and result.get("status") == "auto_assigned":
                    topic = result.get("topic", "")
                    if topic:
                        assigned_topics.add(topic)
                        write_topic_to_file(str(md_file), topic)
                        try:
                            move_file_to_notes_topic_folder(str(md_file), topic)
                        except Exception as e:
                            sys.stderr.write(f"[topics_handler] move error: {e}\n")
                    auto_assigned += 1
                elif result and result.get("status") == "pending":
                    need_confirm += 1
                else:
                    skipped += 1
            except Exception as e:
                sys.stderr.write(f"[topics_handler] batch assign error {md_file}: {e}\n")
                skipped += 1

            if i % 10 == 0:
                self._send_progress("topic-assign-progress", int((i + 1) / total * 100),
                                    f"处理中 {i + 1}/{total}")

        for topic in assigned_topics:
            self._start_task(f"cascade_update_{topic}", self._do_cascade_survey_update, args=(topic,))

        return {
            "success": True,
            "total": total,
            "auto_assigned": auto_assigned,
            "need_confirm": need_confirm,
            "skipped": skipped,
            "assigned_topics": list(assigned_topics),
        }

    def _move_file_to_topic(self, params):
        path = params.get("path", "")
        if not path:
            return {"success": False, "message": "未指定文件"}
        topic = params.get("topic", "").strip()
        if not topic:
            return {"success": False, "message": "未指定目标主题"}
        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)
        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}
        from utils.topic_assigner import write_topic_to_file, move_file_to_notes_topic_folder
        try:
            write_topic_to_file(str(full_path), topic)
            move_file_to_notes_topic_folder(str(full_path), topic)
            self._start_task(f"cascade_update_{topic}", self._do_cascade_survey_update, args=(topic,))
            return {"success": True, "message": f"已移动到主题「{topic}」"}
        except Exception as e:
            return {"success": False, "message": f"移动失败: {str(e)}"}

    def _create_topic(self, params):
        topic_name = params.get("name", "").strip()
        parent = params.get("parent", "").strip()
        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}
        if parent:
            topic_full = f"{parent}/{topic_name}"
        else:
            topic_full = topic_name
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        from utils.topic_assigner import create_topic as wiki_create_topic
        result = wiki_create_topic(topic_full)
        if not result.get("success"):
            return result

        from sidecar.cascade import ensure_topic_folder, append_changelog
        folder_result = ensure_topic_folder(topic_full)
        if folder_result.get("success"):
            append_changelog(f"创建主题: {topic_full}")

        from utils.topic_assigner import auto_assign_topic_for_file, write_topic_to_file, move_file_to_notes_topic_folder
        assigned = 0
        ws = Path(workspace)
        for md_file in ws.rglob("*.md"):
            if md_file.name.startswith(".") or "wiki" in md_file.parts:
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
                meta, _ = self._parse_frontmatter(text)
                if meta and meta.get("topic"):
                    continue
                result2 = auto_assign_topic_for_file(str(md_file))
                if result2 and result2.get("status") == "auto_assigned" and result2.get("topic") == topic_full:
                    write_topic_to_file(str(md_file), topic_full)
                    move_file_to_notes_topic_folder(str(md_file), topic_full)
                    assigned += 1
            except Exception:
                pass

        msg = f"主题「{topic_full}」创建成功"
        if assigned > 0:
            msg += f"，自动分配 {assigned} 个文件"

        return {"success": True, "message": msg, "topic": topic_full}

    def _rename_topic(self, params):
        old_name = params.get("old_name", "").strip()
        new_name = params.get("new_name", "").strip()
        if not old_name or not new_name:
            return {"success": False, "message": "主题名不能为空"}
        if old_name == new_name:
            return {"success": True, "message": "主题名相同"}
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        workspace_path = Path(workspace)
        import shutil
        wiki_path = workspace_path / "wiki" / "WIKI.md"
        if not wiki_path.exists():
            wiki_path = workspace_path / "WIKI.md"
        if not wiki_path.exists():
            return {"success": False, "message": "WIKI.md 不存在"}

        try:
            wiki_text = wiki_path.read_text(encoding='utf-8')
            lines = wiki_text.split('\n')
            old_leaf = old_name.split('/')[-1]
            new_leaf = new_name.split('/')[-1]
            current_parent = ''

            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('## '):
                    current_parent = stripped[3:].strip()
                    if current_parent == old_name:
                        lines[i] = line.replace(old_name, new_name, 1)
                elif stripped.startswith('### '):
                    child = stripped[4:].strip()
                    full = f"{current_parent}/{child}" if current_parent else child
                    if full == old_name:
                        lines[i] = line.replace(child, new_leaf, 1)
            wiki_path.write_text('\n'.join(lines), encoding='utf-8')

            updated_count = 0
            for md_file in workspace_path.rglob('*.md'):
                if md_file.name.startswith('.') or 'wiki' in md_file.parts:
                    continue
                try:
                    text = md_file.read_text(encoding='utf-8')
                    had_bom = text.startswith('\ufeff')
                    meta, body = self._parse_frontmatter(text)
                    if meta is None:
                        continue
                    changed = False
                    if isinstance(meta.get('topic'), str) and meta['topic'] == old_name:
                        meta['topic'] = new_name
                        changed = True
                    if changed:
                        new_fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
                        prefix = '\ufeff' if had_bom else ''
                        new_content = prefix + '---\n' + new_fm + '\n---\n' + body.lstrip('\n')
                        md_file.write_text(new_content, encoding='utf-8')
                        updated_count += 1
                except Exception as e:
                    sys.stderr.write(f"[rename_topic] error processing {md_file}: {e}\n")
                    sys.stderr.flush()

            old_notes_dir = workspace_path / config.NOTES_FOLDER / old_name
            new_notes_dir = workspace_path / config.NOTES_FOLDER / new_name
            if old_notes_dir.exists() and not new_notes_dir.exists():
                new_notes_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_notes_dir), str(new_notes_dir))

            return {"success": True, "message": f"已重命名主题，更新 {updated_count} 个文件", "updated": updated_count}
        except Exception as e:
            return {"success": False, "message": f"重命名失败: {str(e)}"}

    def _delete_topic(self, params):
        topic_name = params.get("topic_name", "").strip()
        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        import shutil
        from pathlib import Path
        workspace_path = Path(workspace)

        wiki_path = workspace_path / "wiki" / "WIKI.md"
        if not wiki_path.exists():
            wiki_path = workspace_path / "WIKI.md"
        if not wiki_path.exists():
            return {"success": False, "message": "WIKI.md 不存在"}

        is_parent = '/' not in topic_name
        if is_parent:
            wiki_text = wiki_path.read_text(encoding='utf-8')
            lines = wiki_text.split('\n')
            current_parent = ''
            children = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('## '):
                    current_parent = stripped[3:].strip()
                elif stripped.startswith('### ') and current_parent == topic_name:
                    children.append(stripped[4:].strip())
            if children:
                return {"success": False, "message": f"无法删除：该主题下还有 {len(children)} 个子主题（{', '.join(children[:3])}{'...' if len(children) > 3 else ''}），请先删除所有子主题"}

        notes_topic_dir = workspace_path / config.NOTES_FOLDER / topic_name
        notes_root = workspace_path / config.NOTES_FOLDER
        moved_files = []

        if notes_topic_dir.exists() and notes_topic_dir.is_dir():
            if is_parent:
                for f in notes_topic_dir.iterdir():
                    if f.is_file() and f.suffix.lower() == ".md":
                        dst = notes_root / f.name
                        if dst.exists():
                            stem = f.stem; counter = 1
                            while dst.exists():
                                dst = notes_root / f"{stem}_{counter}{f.suffix}"
                                counter += 1
                        try:
                            shutil.move(str(f), str(dst))
                            moved_files.append(dst)
                        except Exception as e:
                            sys.stderr.write(f"[delete_topic] move failed: {e}\n")
                            sys.stderr.flush()
            else:
                for f in notes_topic_dir.rglob("*"):
                    if f.is_file() and f.suffix.lower() == ".md":
                        dst = notes_root / f.name
                        if dst.exists():
                            stem = f.stem; counter = 1
                            while dst.exists():
                                dst = notes_root / f"{stem}_{counter}{f.suffix}"
                                counter += 1
                        try:
                            shutil.move(str(f), str(dst))
                            moved_files.append(dst)
                        except Exception as e:
                            sys.stderr.write(f"[delete_topic] move failed: {e}\n")
                            sys.stderr.flush()

        if notes_topic_dir.exists():
            try: shutil.rmtree(str(notes_topic_dir))
            except Exception as e: sys.stderr.write(f"[delete_topic] rmdir: {e}\n")
        org_dir = workspace_path / config.ABSTRACT_FOLDER / topic_name
        if org_dir.exists():
            try: shutil.rmtree(str(org_dir))
            except Exception as e: sys.stderr.write(f"[delete_topic] rmdir org: {e}\n")

        try:
            wiki_text = wiki_path.read_text(encoding='utf-8')
            lines = wiki_text.split('\n')
            new_lines = []
            in_section = False
            in_parent = False
            current_parent = ''
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('## '):
                    current_parent = stripped[3:].strip()
                    if is_parent:
                        if current_parent == topic_name:
                            in_section = True
                            continue
                        else:
                            in_section = False
                    else:
                        if current_parent == topic_name.split('/')[0]:
                            in_parent = True
                        else:
                            in_parent = False
                        in_section = False
                elif stripped.startswith('### ') and in_parent and not is_parent:
                    child = stripped[4:].strip()
                    full = f"{current_parent}/{child}"
                    if full == topic_name:
                        in_section = True
                        continue
                    else:
                        in_section = False
                if in_section:
                    continue
                new_lines.append(line)
            wiki_path.write_text('\n'.join(new_lines), encoding='utf-8')

            updated_count = 0
            for md_file in workspace_path.rglob('*.md'):
                if md_file.name.startswith('.') or 'wiki' in md_file.parts:
                    continue
                try:
                    text = md_file.read_text(encoding='utf-8')
                    had_bom = text.startswith('\ufeff')
                    meta, body = self._parse_frontmatter(text)
                    if meta is None:
                        continue
                    changed = False
                    if isinstance(meta.get('topic'), str) and meta['topic'] == topic_name:
                        meta.pop('topic', None)
                        changed = True
                    if changed:
                        if meta:
                            new_fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
                            prefix = '\ufeff' if had_bom else ''
                            new_content = prefix + '---\n' + new_fm + '\n---\n' + body.lstrip('\n')
                        else:
                            prefix = '\ufeff' if had_bom else ''
                            new_content = prefix + body.lstrip('\n')
                        md_file.write_text(new_content, encoding='utf-8')
                        updated_count += 1
                except Exception as e:
                    sys.stderr.write(f"[delete_topic] error processing {md_file}: {e}\n")
                    sys.stderr.flush()

            # 5. Auto-assign new topics for moved files
            from utils.topic_assigner import auto_assign_topic_for_file, write_topic_to_file, move_file_to_notes_topic_folder
            reassigned = 0; pending = 0
            for f in moved_files:
                if not f.exists(): continue
                try:
                    result = auto_assign_topic_for_file(str(f))
                    if result and result.get("status") == "auto_assigned" and result.get("topic"):
                        write_topic_to_file(str(f), result["topic"])
                        move_file_to_notes_topic_folder(str(f), result["topic"])
                        reassigned += 1
                    else:
                        pending += 1
                except Exception as e:
                    sys.stderr.write(f"[delete_topic] reassign failed: {e}\n")
                    pending += 1

            return {"success": True, "message": f"已删除主题「{topic_name}」，{len(moved_files)} 个文件移至 Notes 根目录，重新分配 {reassigned} 个，{pending} 个待确认",
                    "moved": len(moved_files), "updated": updated_count, "reassigned": reassigned, "pending": pending}
        except Exception as e:
            return {"success": False, "message": f"删除失败: {str(e)}"}

    def _get_all_topic_names(self, params):
        wiki_path = Path(config.workspace_path) / "wiki" / "WIKI.md"
        if not wiki_path.exists():
            wiki_path = Path(config.workspace_path) / "WIKI.md"
        if not wiki_path.exists():
            return {"success": True, "topics": []}
        try:
            text = wiki_path.read_text(encoding='utf-8')
            topics = []
            current_parent = ''
            for line in text.split('\n'):
                stripped = line.rstrip()
                if stripped.startswith('## '):
                    current_parent = stripped[3:].strip()
                    topics.append(current_parent)
                elif stripped.startswith('### '):
                    child = stripped[4:].strip()
                    full = f"{current_parent}/{child}" if current_parent else child
                    topics.append(full)
            return {"success": True, "topics": topics}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _get_file_topics(self, params):
        path = params.get("path", "")
        if not path:
            return {"success": False, "message": "未指定文件"}
        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)
        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}
        try:
            text = full_path.read_text(encoding='utf-8')
            fm, _ = self._parse_frontmatter(text)
            if fm is None:
                return {"success": True, "topics": []}
            t = fm.get("topic", "")
            return {"success": True, "topics": [t] if t else []}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _get_topic_files(self, params):
        topic_name = params.get("topic", "").strip()
        workspace = config.workspace_path
        workspace_path = Path(workspace)
        if not topic_name or not workspace or not workspace_path.exists():
            return {"success": True, "files": []}
        files = []
        for md_file in sorted(workspace_path.rglob('*.md')):
            if md_file.name.startswith('.') or 'wiki' in md_file.parts:
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                fm, _ = self._parse_frontmatter(text)
                if fm is None:
                    continue
                file_topic = fm.get("topic", "")
                if file_topic and file_topic.strip().strip("'\"") == topic_name:
                    files.append(str(md_file.relative_to(workspace_path)))
            except Exception:
                continue
        return {"success": True, "files": files, "topic": topic_name}

    def _remove_file_from_topic(self, params):
        path = params.get("path", "")
        topic_name = params.get("topic", "").strip()
        if not path or not topic_name:
            return {"success": False, "message": "参数缺失"}
        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)
        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}
        try:
            text = full_path.read_text(encoding='utf-8')
            had_bom = text.startswith('\ufeff')
            meta, body = self._parse_frontmatter(text)
            if meta is None:
                return {"success": True, "message": "无需修改"}
            if isinstance(meta.get("topic"), str) and meta["topic"] == topic_name:
                meta.pop("topic", None)
                if meta:
                    new_fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
                    prefix = '\ufeff' if had_bom else ''
                    new_content = prefix + '---\n' + new_fm + '\n---\n' + body.lstrip('\n')
                else:
                    prefix = '\ufeff' if had_bom else ''
                    new_content = prefix + body.lstrip('\n')
                full_path.write_text(new_content, encoding='utf-8')
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _do_cascade_survey_update(self, topic):
        from sidecar.cascade import ensure_topic_folder, collect_topic_notes, update_existing_survey, get_survey_path, generate_new_survey, append_changelog
        try:
            ensure_topic_folder(topic)
            notes = collect_topic_notes(topic)
            if notes:
                survey_path = get_survey_path(topic)
                if survey_path and survey_path.exists():
                    update_existing_survey(topic, notes)
                else:
                    generate_new_survey(topic, notes)
                append_changelog(f"自动更新主题综述: {topic}")
        except Exception as e:
            sys.stderr.write(f"[topics_handler] cascade survey update failed: {e}\n")

    def _do_file_added_cascade(self, file_path: Path):
        from sidecar.cascade import cascade_on_topic_resolved
        try:
            text = file_path.read_text(encoding="utf-8")
            fm, _ = self._parse_frontmatter(text)
            topic = fm.get("topic") if fm else None
            if topic:
                self._start_task(f"cascade_{topic}_{file_path.stem}", cascade_on_topic_resolved, args=(str(file_path), topic))
        except Exception as e:
            sys.stderr.write(f"[topics_handler] file_added_cascade error: {e}\n")

    def _get_all_pending(self, params):
        from utils.topic_assigner import load_pending, cleanup_stale_pending
        from utils.link_indexer import get_backlinks, cleanup_stale_links

        cleanup_stale_pending()
        cleanup_stale_links()

        pending_topics = load_pending()
        items = []
        for p in pending_topics:
            items.append({
                "type": "topic",
                "file": p.get("file", ""),
                "title": p.get("title", ""),
                "candidates": p.get("candidates", []),
                "source": p.get("source", ""),
            })

        try:
            links_data = get_backlinks("")
            for link in links_data.get("links", []):
                if link.get("status") == "pending":
                    items.append({
                        "type": "link",
                        "source": link.get("from", ""),
                        "target": link.get("to", ""),
                        "context": link.get("reason", ""),
                    })
        except Exception:
            pass

        return {"items": items, "count": len(items)}

    def _resolve_topic(self, params):
        file_path = params.get("file_path", "")
        topic = params.get("topic", "").strip()
        if not file_path or not topic:
            return {"success": False, "message": "参数缺失"}
        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)
        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}

        from utils.topic_assigner import write_topic_to_file, move_file_to_notes_topic_folder, add_file_to_wiki_topic, load_pending, save_pending

        result = write_topic_to_file(str(full_path), topic)
        if not result.get("success"):
            return result

        move_file_to_notes_topic_folder(str(full_path), topic)

        workspace = config.workspace_path
        try:
            rel_path = str(full_path.relative_to(workspace)) if full_path.is_relative_to(workspace) else str(full_path)
        except ValueError:
            rel_path = str(full_path)
        file_title = full_path.stem
        add_file_to_wiki_topic(rel_path, topic, file_title)

        pending = load_pending()
        pending = [p for p in pending if p.get("file") != rel_path]
        save_pending(pending)

        self._start_task(f"cascade_{topic}_{full_path.stem}", self._do_cascade_survey_update, args=(topic,))

        return {"success": True, "message": f"已确认主题「{topic}」"}

    def _get_activity_log(self, params):
        from utils.activity_log import get_entries
        limit = params.get("limit", 50)
        return {"entries": get_entries(limit)}

    def _merge_duplicate_topics(self, params):
        from utils.topic_assigner import _merge_duplicate_topics_in_wiki, _deduplicate_files_in_wiki
        merged = _merge_duplicate_topics_in_wiki()
        deduped = _deduplicate_files_in_wiki()
        return {"success": True, "merged_topics": merged, "deduplicated_files": deduped}

    def register_routes(self, router):
        router.register("get_topic_tree", self._get_topic_tree)
        router.register("auto_assign_topic", self._auto_assign_topic)
        router.register("batch_auto_assign_topics", self._batch_auto_assign_topics)
        router.register("move_file_to_topic", self._move_file_to_topic)
        router.register("create_topic", self._create_topic)
        router.register("rename_topic", self._rename_topic)
        router.register("delete_topic", self._delete_topic)
        router.register("resolve_topic", self._resolve_topic)
        router.register("get_all_topic_names", self._get_all_topic_names)
        router.register("get_file_topics", self._get_file_topics)
        router.register("get_topic_files", self._get_topic_files)
        router.register("remove_file_from_topic", self._remove_file_from_topic)
        router.register("get_all_pending", self._get_all_pending)
        router.register("get_activity_log", self._get_activity_log)
        router.register("merge_duplicate_topics", self._merge_duplicate_topics)
        router.register("get_survey_status", self._get_survey_status)
        router.register("toggle_survey", self._toggle_survey)

    def _get_survey_status(self, params):
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}
        workspace_path = Path(workspace)
        wiki_path = workspace_path / "wiki" / "WIKI.md"
        if not wiki_path.exists():
            wiki_path = workspace_path / "WIKI.md"
        if not wiki_path.exists():
            return {"success": True, "surveys": {}}
        try:
            text = wiki_path.read_text(encoding='utf-8')
            lines = text.split('\n')
            surveys = {}
            current_parent = ''
            i = 0
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith('## '):
                    current_parent = stripped[3:].strip()
                    is_off = False
                    if i + 1 < len(lines) and lines[i + 1].strip() == '> 综述: off':
                        is_off = True
                    surveys[current_parent] = not is_off
                elif stripped.startswith('### ') and current_parent:
                    child = stripped[4:].strip()
                    full = f"{current_parent}/{child}"
                    parent_on = surveys.get(current_parent, True)
                    if parent_on:
                        surveys[full] = False
                    else:
                        is_off = False
                        if i + 1 < len(lines) and lines[i + 1].strip() == '> 综述: off':
                            is_off = True
                        surveys[full] = not is_off
                i += 1
            return {"success": True, "surveys": surveys}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _toggle_survey(self, params):
        topic_name = params.get("topic", "").strip()
        if not topic_name:
            return {"success": False, "message": "未指定主题"}
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}
        workspace_path = Path(workspace)
        wiki_path = workspace_path / "wiki" / "WIKI.md"
        if not wiki_path.exists():
            wiki_path = workspace_path / "WIKI.md"
        if not wiki_path.exists():
            return {"success": False, "message": "WIKI.md 不存在"}

        try:
            text = wiki_path.read_text(encoding='utf-8')
            lines = text.split('\n')
            new_lines = []
            current_parent = ''
            is_parent = '/' not in topic_name
            target_leaf = topic_name.split('/')[-1] if not is_parent else topic_name
            i = 0

            while i < len(lines):
                stripped = lines[i].strip()
                new_lines.append(lines[i])

                if stripped.startswith('## '):
                    current_parent = stripped[3:].strip()

                    if is_parent:
                        if current_parent == topic_name:
                            if i + 1 < len(lines) and lines[i + 1].strip() == '> 综述: off':
                                i += 1
                            else:
                                new_lines.append('> 综述: off')
                                i += 1
                            i += 1
                            while i < len(lines):
                                s = lines[i].strip()
                                if s.startswith('## '):
                                    new_lines.append(lines[i])
                                    i += 1
                                    break
                                elif s.startswith('### ') and current_parent:
                                    child = s[4:].strip()
                                    full = f"{current_parent}/{child}"
                                    new_lines.append(lines[i])
                                    i += 1
                                    if i < len(lines) and lines[i].strip() == '> 综述: off':
                                        i += 1
                                    while i < len(lines):
                                        ns = lines[i].strip()
                                        if ns.startswith('## ') or ns.startswith('### '):
                                            break
                                        new_lines.append(lines[i])
                                        i += 1
                                else:
                                    new_lines.append(lines[i])
                                    i += 1
                                    if s.startswith('## '):
                                        break
                            continue
                elif stripped.startswith('### ') and current_parent and not is_parent:
                    child = stripped[4:].strip()
                    full = f"{current_parent}/{child}"
                    if full == topic_name:
                        if i + 1 < len(lines) and lines[i + 1].strip() == '> 综述: off':
                            i += 1
                        else:
                            new_lines.append('> 综述: off')
                            i += 1
                        i += 1
                        continue

                i += 1

            wiki_path.write_text('\n'.join(new_lines), encoding='utf-8')
            return {"success": True, "message": "已切换综述状态"}
        except Exception as e:
            return {"success": False, "message": str(e)}
