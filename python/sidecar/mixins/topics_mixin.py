"""Topic tree, batch assign, topic CRUD, file moves, add tag to file (from python/main.py)."""

import json
import re
import sys
import shutil
import threading
from pathlib import Path

import yaml
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

        save_pending([])

        files_to_process = 0
        auto_assigned_count = 0
        skipped = 0

        for md_file in md_files:
            try:
                text = md_file.read_text(encoding='utf-8')
            except Exception:
                skipped += 1
                continue

            m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
            if not m:
                skipped += 1
                continue

            if not _check_topic_needs_processing(m.group(1)):
                skipped += 1
                continue

            result = auto_assign_topic_for_file(str(md_file))
            files_to_process += 1
            if result and result.get("status") == "auto_assigned":
                auto_assigned_count += 1

        pending = load_pending()
        need_confirm = len(pending)
        auto_assigned = auto_assigned_count

        return {
            "success": True,
            "total": len(md_files),
            "auto_assigned": auto_assigned,
            "need_confirm": need_confirm,
            "skipped": skipped,
            "pending": pending
        }

    def _create_topic(self, params):
        from utils.topic_assigner import create_topic
        topic_name = params.get("name", "")
        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}
        return create_topic(topic_name)

    def _get_pending_topics(self, params):
        from utils.topic_assigner import load_pending
        return {"pending": load_pending()}

    def _resolve_topic(self, params):
        from utils.topic_assigner import write_topic_to_file, load_pending, save_pending, add_file_to_wiki_topic
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

        return {"success": True, "topic": topic}

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

        return move_file_to_topic(file_path, new_topic)

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
