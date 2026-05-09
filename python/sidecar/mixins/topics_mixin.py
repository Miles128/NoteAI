"""Topic tree, batch assign, topic CRUD, file moves, add tag to file (from python/main.py)."""

import sys
from pathlib import Path

from config import config, is_ignored_dir

class TopicsMixin:
    def _get_topic_tree(self, params):
        from utils.topic_assigner import parse_wiki_structure

        try:
            topics = parse_wiki_structure()
        except Exception as e:
            sys.stderr.write(f"[topic_tree] parse_wiki_structure failed: {e}\n")
            sys.stderr.flush()
            topics = []

        try:
            pending = self._load_pending_topics()
        except Exception:
            pending = []

        topics.sort(key=lambda t: t.get("name", "").lower())

        return {"topics": topics, "pending": pending}

    def _auto_assign_topic(self, params):
        from utils.topic_assigner import auto_assign_topic_for_file, load_pending, parse_wiki_headings, write_topic_to_file
        file_path = params.get("file_path", "")
        if not file_path:
            return {"success": False, "message": "未指定文件"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)

        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}

        auto_assign_topic_for_file(str(full_path))

        pending = load_pending()
        for p in pending:
            if p.get("file") == file_path:
                return {"success": True, "pending": True, "candidates": p.get("candidates", []), "source": p.get("source", "")}

        return {"success": True, "topic": None, "message": "主题已分配或无法自动分配"}

    def _batch_auto_assign_topics(self, params):
        from utils.topic_assigner import auto_assign_topic_for_file, load_pending, save_pending, _check_topic_needs_processing
        import re

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        wiki_path = Path(workspace) / "WIKI.md"
        if not wiki_path.exists():
            return {"success": False, "message": "WIKI.md 不存在，请先提取主题"}

        excluded_dirs = {'AI Wiki', '.git', '.obsidian', '.trash'}
        md_files = []
        for folder in Path(workspace).iterdir():
            if not folder.is_dir():
                continue
            if folder.name in excluded_dirs or folder.name.startswith('.'):
                continue
            for md_file in folder.rglob('*.md'):
                if md_file.name.startswith('.'):
                    continue
                if any(is_ignored_dir(p.name) for p in md_file.relative_to(workspace).parents):
                    continue
                md_files.append(md_file)

        files_to_process = 0
        auto_assigned_count = 0
        skipped = 0
        format_optimized_count = 0
        auto_assigned_files = {}

        for md_file in md_files:
            try:
                text = md_file.read_text(encoding='utf-8')
            except Exception:
                skipped += 1
                continue

            m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
            if m and not _check_topic_needs_processing(m.group(1)):
                skipped += 1
                continue

            files_to_process += 1
            file_name = md_file.name

            self._send_response({
                "id": "event",
                "result": {
                    "type": "batch_assign_progress",
                    "file": file_name,
                    "current": files_to_process,
                    "message": f"正在处理: {file_name}"
                }
            })

            result = auto_assign_topic_for_file(str(md_file))

            if result and result.get("format_optimized"):
                format_optimized_count += 1
                self._send_response({
                    "id": "event",
                    "result": {
                        "type": "batch_assign_progress",
                        "file": file_name,
                        "message": f"已优化格式: {file_name}"
                    }
                })

            if result and result.get("status") == "auto_assigned":
                auto_assigned_count += 1
                topic = result.get("topic", "")
                source = result.get("source", "keyword")
                if topic:
                    if topic not in auto_assigned_files:
                        auto_assigned_files[topic] = []
                    auto_assigned_files[topic].append(str(md_file))
                    self._send_response({
                        "id": "event",
                        "result": {
                            "type": "batch_assign_progress",
                            "file": file_name,
                            "message": f"已分配主题「{topic}」: {file_name}" + (" (LLM)" if source == "llm" else "")
                        }
                    })
            elif result and result.get("status") == "pending":
                candidates = result.get("candidates", [])
                self._send_response({
                    "id": "event",
                    "result": {
                        "type": "batch_assign_progress",
                        "file": file_name,
                        "message": f"待确认主题: {file_name}" + (f" (候选: {', '.join(candidates[:3])})" if candidates else " (无候选)")
                    }
                })

        pending = load_pending()
        need_confirm = len(pending)
        auto_assigned = auto_assigned_count

        for topic, file_paths in auto_assigned_files.items():
            for fp in file_paths:
                self._start_task(f"cascade_{topic}_{Path(fp).stem}", self._do_cascade_on_resolve, args=(fp, topic))

        summary_parts = []
        if auto_assigned > 0:
            summary_parts.append(f"自动分配 {auto_assigned} 个文件")
        if need_confirm > 0:
            summary_parts.append(f"{need_confirm} 个待确认")
        if format_optimized_count > 0:
            summary_parts.append(f"优化 {format_optimized_count} 个格式")
        if not summary_parts:
            summary_parts.append("所有文件主题已分配")

        self._send_response({
            "id": "event",
            "result": {
                "type": "batch_assign_progress",
                "message": "完成 - " + "，".join(summary_parts)
            }
        })

        return {
            "success": True,
            "total": len(md_files),
            "auto_assigned": auto_assigned,
            "need_confirm": need_confirm,
            "skipped": skipped,
            "format_optimized": format_optimized_count,
            "pending": pending
        }

    def _create_topic(self, params):
        from utils.topic_assigner import create_topic
        from sidecar.cascade import ensure_topic_folder, collect_topic_notes, generate_new_survey, append_changelog
        topic_name = params.get("name", "")
        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}

        result = create_topic(topic_name)
        if not result.get("success"):
            return result

        ensure_topic_folder(topic_name)

        notes = collect_topic_notes(topic_name)
        if notes:
            survey_result = generate_new_survey(topic_name, notes)
            if survey_result.get("success"):
                append_changelog(f"创建主题并生成综述: {topic_name}")
            else:
                append_changelog(f"创建主题「{topic_name}」但综述生成失败: {survey_result.get('message', '')}")
        else:
            append_changelog(f"创建主题「{topic_name}」（暂无笔记，跳过综述生成）")

        return result

    def _get_pending_topics(self, params):
        from utils.topic_assigner import load_pending
        return {"pending": load_pending()}

    def _get_all_pending(self, params):
        from utils.topic_assigner import load_pending
        from utils.link_indexer import get_backlinks

        items = []

        pending_topics = load_pending()
        for p in pending_topics:
            items.append({
                "type": "topic",
                "file": p.get("file", ""),
                "title": p.get("title", ""),
                "candidates": p.get("candidates", []),
                "source": p.get("source", ""),
            })

        try:
            links_data = get_backlinks()
            for link in links_data:
                if link.get("status") == "pending":
                    items.append({
                        "type": "link",
                        "source": link.get("source", ""),
                        "target": link.get("target", ""),
                        "context": link.get("context", ""),
                    })
        except Exception:
            pass

        return {"items": items, "count": len(items)}

    def _resolve_topic(self, params):
        from utils.topic_assigner import write_topic_to_file, load_pending, save_pending, add_file_to_wiki_topic, move_file_to_notes_topic_folder
        file_path = params.get("file_path", "")
        topic = params.get("topic", "")
        if not file_path or not topic:
            return {"success": False, "message": "参数不完整"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        write_topic_to_file(full_path, topic)

        pending = load_pending()
        file_title = None
        for p in pending:
            if p.get("file") == file_path:
                file_title = p.get("title")
                break

        pending = [p for p in pending if p.get("file") != file_path]
        save_pending(pending)

        add_file_to_wiki_topic(file_path, topic, file_title)

        move_file_to_notes_topic_folder(full_path, topic)

        self._start_task(f"cascade_{topic}_{Path(full_path).stem}", self._do_cascade_on_resolve, args=(full_path, topic))

        return {"success": True, "topic": topic}

    def _do_cascade_on_resolve(self, file_path, topic):
        from sidecar.cascade import cascade_on_topic_resolved

        def on_chunk(token):
            self._send_response({
                "id": "event",
                "result": {
                    "type": "cascade_survey_chunk",
                    "topic": topic,
                    "token": token,
                }
            })

        try:
            result = cascade_on_topic_resolved(file_path, topic, on_chunk=on_chunk)
            self._send_response({
                "id": "event",
                "result": {
                    "type": "cascade_done",
                    "topic": topic,
                    "data": result,
                }
            })
        except Exception as e:
            sys.stderr.write(f"[cascade] cascade_on_topic_resolved failed: {e}\n")
            sys.stderr.flush()

    def _do_cascade_survey_update(self, topic):
        from sidecar.cascade import collect_topic_notes, generate_new_survey, get_survey_path, update_existing_survey, append_changelog

        try:
            notes = collect_topic_notes(topic)
            if not notes:
                survey_path = get_survey_path(topic)
                if survey_path and survey_path.exists():
                    survey_path.unlink()
                return

            survey_path = get_survey_path(topic)
            if survey_path and survey_path.exists():
                result = generate_new_survey(topic, notes)
            else:
                result = generate_new_survey(topic, notes)

            if result.get("success"):
                append_changelog(f"更新综述（文件变动）: {topic}")
        except Exception as e:
            sys.stderr.write(f"[cascade] survey update failed for {topic}: {e}\n")
            sys.stderr.flush()

    def _rename_topic(self, params):
        from utils.topic_assigner import rename_topic
        old_topic = params.get("old_topic", "")
        new_topic = params.get("new_topic", "")
        if not old_topic or not new_topic:
            return {"success": False, "message": "参数不完整"}

        return rename_topic(old_topic, new_topic)

    def _sync_wiki_with_files(self, params):
        from utils.topic_assigner import sync_wiki_with_files
        return sync_wiki_with_files()

    def _delete_topic(self, params):
        from utils.topic_assigner import delete_topic
        topic_name = params.get("topic_name", "")
        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}
        return delete_topic(topic_name)

    def _move_file_to_topic(self, params):
        from utils.topic_assigner import move_file_to_topic
        file_path = params.get("file_path", "")
        new_topic = params.get("new_topic", "")
        if not file_path or not new_topic:
            return {"success": False, "message": "参数不完整"}

        result = move_file_to_topic(file_path, new_topic)

        if result.get("success"):
            msg = result.get("message", "")
            old_topic = None
            if "「" in msg and "」" in msg:
                import re as _re
                m = _re.search(r'从「(.+?)」', msg)
                if m:
                    old_topic = m.group(1)

            full_path = self._resolve_path(file_path)
            if full_path:
                self._start_task(f"cascade_{new_topic}_{Path(full_path).stem}", self._do_cascade_on_resolve, args=(full_path, new_topic))
            if old_topic and old_topic != new_topic:
                self._start_task(f"cascade_update_{old_topic}", self._do_cascade_survey_update, args=(old_topic,))

        return result

    def _move_file(self, params):
        import shutil
        file_path = params.get("file_path", "")
        target_folder = params.get("target_folder", "")

        if not file_path or not target_folder:
            return {"success": False, "message": "参数不完整"}

        src = self._resolve_path(file_path)
        dst_dir = self._resolve_path(target_folder)
        if not src or not dst_dir:
            return {"success": False, "message": "路径无效"}

        src = Path(src)
        dst_dir = Path(dst_dir)

        if not src.exists():
            return {"success": False, "message": f"源文件不存在: {file_path}"}

        if not dst_dir.exists() or not dst_dir.is_dir():
            return {"success": False, "message": f"目标文件夹不存在: {target_folder}"}

        dst = dst_dir / src.name
        if dst.exists():
            return {"success": False, "message": f"目标已存在同名文件: {dst.name}"}

        if src.is_dir():
            try:
                dst.resolve().relative_to(src.resolve())
                return {"success": False, "message": "不能将文件夹移动到其自身或子文件夹中"}
            except ValueError:
                pass

        workspace = config.workspace_path
        try:
            shutil.move(str(src), str(dst))
            new_rel_path = str(dst.relative_to(workspace))
            return {"success": True, "message": f"已移动到 {new_rel_path}", "new_path": new_rel_path}
        except Exception as e:
            return {"success": False, "message": f"移动失败: {e}"}

    def _add_tag_to_file(self, params):
        import re
        file_path = params.get("file_path", "")
        tag = params.get("tag", "")

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        if not file_path or not tag:
            return {"success": False, "message": "参数不完整"}

        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)

        if not full_path.exists():
            return {"success": False, "message": f"文件不存在: {file_path}"}

        if not full_path.suffix.lower() == '.md':
            return {"success": False, "message": "仅支持 Markdown 文件"}

        try:
            text = full_path.read_text(encoding='utf-8')
            had_bom = text.startswith('\ufeff')
            clean_text = text.lstrip('\ufeff')

            m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', clean_text)
            if not m:
                prefix = '\ufeff' if had_bom else ''
                frontmatter = '---\ntags: [' + tag + ']\n---\n'
                full_path.write_text(prefix + frontmatter + clean_text, encoding='utf-8')
                self._save_tags_md({})
                return {"success": True, "message": f"已添加标签「{tag}」"}

            yaml_text = m.group(2)
            lines = yaml_text.split('\n')
            tags_line_idx = None
            existing_tags = []
            list_end_idx = None

            for i, line in enumerate(lines):
                idx = line.find(':')
                if idx < 0:
                    continue
                key = line[:idx].strip()
                val = line[idx + 1:].strip()
                if key == 'tags':
                    tags_line_idx = i
                    if val.startswith('[') and val.endswith(']'):
                        existing_tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
                    elif val.startswith('- '):
                        existing_tags.append(val[2:].strip().strip("'\""))
                        j = i + 1
                        while j < len(lines) and lines[j].strip().startswith('- '):
                            existing_tags.append(lines[j].strip()[2:].strip().strip("'\""))
                            j += 1
                        list_end_idx = j
                    elif val:
                        existing_tags = [val.strip().strip("'\"")]
                    break

            if tag in existing_tags:
                return {"success": True, "message": f"标签「{tag}」已存在，无需重复添加"}

            all_tags = existing_tags + [tag]
            new_tags_str = '[' + ', '.join(all_tags) + ']'

            if tags_line_idx is not None:
                if list_end_idx is not None:
                    lines[tags_line_idx] = 'tags: ' + new_tags_str
                    del lines[tags_line_idx + 1:list_end_idx]
                else:
                    lines[tags_line_idx] = 'tags: ' + new_tags_str
            else:
                lines.append('tags: ' + new_tags_str)

            prefix = '\ufeff' if had_bom else ''
            new_yaml = '\n'.join(lines)
            new_text = prefix + m.group(1) + new_yaml + m.group(3) + clean_text[m.end():]
            full_path.write_text(new_text, encoding='utf-8')
            self._save_tags_md({})
            return {"success": True, "message": f"已添加标签「{tag}」"}
        except Exception as e:
            return {"success": False, "message": f"添加标签失败: {e}"}

    def _get_changelog(self, params):
        from sidecar.cascade import get_changelog
        limit = params.get("limit", 50)
        entries = get_changelog(limit=limit)
        return {"success": True, "entries": entries}

    def _check_and_generate_surveys(self, params):
        from sidecar.cascade import check_and_generate_surveys

        def on_progress(current, total, message):
            self._send_progress("survey_check", current / total if total > 0 else 0, message)

        return check_and_generate_surveys(on_progress=on_progress)
