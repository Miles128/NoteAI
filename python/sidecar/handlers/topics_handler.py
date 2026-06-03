import shutil
import sys
from pathlib import Path

import yaml

from config import config, is_ignored_dir
from config.constants import TOPIC_SEP
from sidecar.cascade import (
    append_changelog,
    cascade_on_topic_resolved,
    collect_topic_notes,
    ensure_topic_folder,
    generate_new_survey,
    get_survey_path,
    update_existing_survey,
)
from sidecar.handlers.base import BaseHandler
from sidecar.mixins.topics_3tier_mixin import Topics3TierMixin
from sidecar.wiki_utils import (
    get_all_topic_names,
    get_survey_status,
    parse_wiki_headings,
    resolve_wiki_path,
    toggle_survey,
)
from utils.activity_log import get_entries
from utils.link_indexer import load_links
from utils.logger import logger
from utils.topic_assigner import (
    _deduplicate_files_in_wiki,
    _merge_duplicate_topics_in_wiki,
    auto_assign_topic_for_file,
    load_pending,
    move_file_to_notes_topic_folder,
    save_pending,
    sync_wiki_with_files,
    write_topic_to_file,
)
from utils.topic_assigner import (
    create_topic as wiki_create_topic,
)
from utils.topic_manager import TopicManager


class TopicsHandler(BaseHandler, Topics3TierMixin):
    def _sync_wiki_with_folder_system(self):
        try:
            return sync_wiki_with_files()
        except Exception as e:
            logger.warning(f"[topics_handler] sync WIKI with folder system failed: {e}\n")
            return {"success": False, "message": str(e)}

    def _topic_dir_path(self, workspace_path: Path, topic_name: str) -> Path:
        normalized = topic_name.replace('/', TOPIC_SEP)
        parts = [p.strip() for p in normalized.split(TOPIC_SEP) if p.strip()]
        topic_dir = workspace_path / config.NOTES_FOLDER
        for part in parts:
            topic_dir = topic_dir / part
        return topic_dir

    def _topic_artifact_dir_path(self, workspace_path: Path, root_folder: str, topic_name: str) -> Path:
        normalized = topic_name.replace('/', TOPIC_SEP)
        parts = [p.strip() for p in normalized.split(TOPIC_SEP) if p.strip()]
        topic_dir = workspace_path / root_folder
        for part in parts:
            topic_dir = topic_dir / part
        return topic_dir

    def _get_topic_tree(self, params):
        return self._get_topic_tree_3tier(params)

    def _parse_wiki_headings(self):
        return parse_wiki_headings()

    def _auto_assign_topic(self, params):  # noqa: PLR0911
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
            result = auto_assign_topic_for_file(str(full_path))
            if not result:
                return {"success": False, "message": "未找到匹配主题"}
            if result.get("status") != "auto_assigned":
                return {"success": False, "message": "需要人工确认主题", "candidates": result.get("candidates", [])}
            topic = result.get("topic", "")
            if not topic:
                return {"success": False, "message": "未找到匹配主题"}
            self._sync_wiki_with_folder_system()
            self._start_task(f"cascade_update_{topic}", self._do_cascade_survey_update, args=(topic,))
            return {"success": True, "topic": topic}
        except Exception as e:
            return {"success": False, "message": f"自动分配失败: {str(e)}"}

    def _batch_auto_assign_topics(self, _params):
        if not config.workspace_path:
            return {"success": False, "message": "未设置工作区或工作区不存在"}

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

        if assigned_topics:
            self._sync_wiki_with_folder_system()

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
        from sidecar.schema_validator import require_topic

        ok, err = require_topic(topic)
        if not ok:
            return {"success": False, "message": err}
        try:
            write_topic_to_file(str(full_path), topic)
            move_file_to_notes_topic_folder(str(full_path), topic)
            self._sync_wiki_with_folder_system()
            self._start_task(f"cascade_update_{topic}", self._do_cascade_survey_update, args=(topic,))
            return {"success": True, "message": f"已移动到主题「{topic}」"}
        except Exception as e:
            return {"success": False, "message": f"移动失败: {str(e)}"}

    def _create_topic(self, params):
        topic_name = params.get("name", "").strip()
        parent = params.get("parent", "").strip()
        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}
        topic_full = TOPIC_SEP.join([parent, topic_name]) if parent else topic_name

        from sidecar.schema_validator import require_topic

        ok, err = require_topic(topic_full)
        if not ok:
            return {"success": False, "message": err}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        result = wiki_create_topic(topic_full)
        if not result.get("success"):
            return result

        folder_result = ensure_topic_folder(topic_full)
        if folder_result.get("success"):
            append_changelog(f"创建主题: {topic_full}")

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
                    assigned += 1
            except Exception:
                pass

        self._sync_wiki_with_folder_system()

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
        try:
            old_notes_dir = self._topic_dir_path(workspace_path, old_name)
            new_notes_dir = self._topic_dir_path(workspace_path, new_name)
            if not old_notes_dir.exists():
                return {"success": False, "message": f"主题文件夹不存在: {old_name}"}

            new_notes_dir.parent.mkdir(parents=True, exist_ok=True)
            merged = False
            if new_notes_dir.exists():
                merged = True
                for item in old_notes_dir.iterdir():
                    dst = new_notes_dir / item.name
                    if dst.exists():
                        stem = item.stem
                        suffix = item.suffix
                        counter = 1
                        while dst.exists():
                            dst = new_notes_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                    shutil.move(str(item), str(dst))
                shutil.rmtree(str(old_notes_dir))
            else:
                shutil.move(str(old_notes_dir), str(new_notes_dir))

            old_abstract_dir = self._topic_artifact_dir_path(workspace_path, config.ABSTRACT_FOLDER, old_name)
            new_abstract_dir = self._topic_artifact_dir_path(workspace_path, config.ABSTRACT_FOLDER, new_name)
            if old_abstract_dir.exists() and not new_abstract_dir.exists():
                new_abstract_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_abstract_dir), str(new_abstract_dir))

            sync_result = self._sync_wiki_with_folder_system()
            updated_count = sync_result.get("updated", 0) if sync_result.get("success") else 0
            return {
                "success": True,
                "message": f"已{'合并' if merged else '重命名'}主题，更新 {updated_count} 个文件",
                "updated": updated_count,
                "merged": merged,
            }
        except Exception as e:
            return {"success": False, "message": f"重命名失败: {str(e)}"}

    def _delete_topic(self, params):
        topic_name = params.get("topic_name", "").strip()
        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        workspace_path = Path(workspace)
        notes_root = workspace_path / config.NOTES_FOLDER
        notes_topic_dir = self._topic_dir_path(workspace_path, topic_name)
        moved_files = []

        if notes_topic_dir.exists() and notes_topic_dir.is_dir():
            for f in sorted(notes_topic_dir.rglob("*.md")):
                dst = notes_root / f.name
                if dst.exists():
                    stem = f.stem
                    counter = 1
                    while dst.exists():
                        dst = notes_root / f"{stem}_{counter}{f.suffix}"
                        counter += 1
                try:
                    shutil.move(str(f), str(dst))
                    moved_files.append(dst)
                except Exception as e:
                    logger.warning(f"[delete_topic] move failed: {e}\n")
            try:
                shutil.rmtree(str(notes_topic_dir))
            except Exception as e:
                sys.stderr.write(f"[delete_topic] rmdir: {e}\n")

        org_dir = self._topic_artifact_dir_path(workspace_path, config.ABSTRACT_FOLDER, topic_name)
        if org_dir.exists():
            try:
                shutil.rmtree(str(org_dir))
            except Exception as e:
                sys.stderr.write(f"[delete_topic] rmdir org: {e}\n")

        try:
            sync_result = self._sync_wiki_with_folder_system()
            updated_count = sync_result.get("updated", 0) if sync_result.get("success") else 0
            return {
                "success": True,
                "message": f"已删除主题「{topic_name}」，{len(moved_files)} 个文件移至 Notes 根目录，更新 {updated_count} 个文件",
                "moved": len(moved_files),
                "updated": updated_count,
            }
        except Exception as e:
            return {"success": False, "message": f"删除失败: {str(e)}"}

    def _get_all_topic_names(self, _params):
        topics = get_all_topic_names()
        return {"success": True, "topics": topics}

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
                notes_root = Path(config.workspace_path) / config.NOTES_FOLDER
                notes_root.mkdir(parents=True, exist_ok=True)
                if full_path.parent != notes_root:
                    dst = notes_root / full_path.name
                    if dst.exists():
                        stem = full_path.stem
                        counter = 1
                        while dst.exists():
                            dst = notes_root / f"{stem}_{counter}{full_path.suffix}"
                            counter += 1
                    shutil.move(str(full_path), str(dst))
                self._sync_wiki_with_folder_system()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _do_cascade_survey_update(self, topic):
        from sidecar.cascade_runner import run_cascade_survey_update

        run_cascade_survey_update(topic, send_response=self._send_response)

    def _do_file_added_cascade(self, file_path: Path):
        try:
            text = file_path.read_text(encoding="utf-8")
            fm, _ = self._parse_frontmatter(text)
            topic = fm.get("topic") if fm else None
            if topic:
                self._start_task(f"cascade_{topic}_{file_path.stem}", cascade_on_topic_resolved, args=(str(file_path), topic))
        except Exception as e:
            sys.stderr.write(f"[topics_handler] file_added_cascade error: {e}\n")

    def _get_all_pending(self, _params):
        workspace = config.workspace_path
        topic_options: list[str] = []
        if workspace:
            try:
                topic_options = TopicManager.collect_topic_labels(workspace)
            except Exception:
                topic_options = []

        from sidecar.pending_items import collect_pending_items

        items = collect_pending_items(workspace)
        return {"items": items, "count": len(items), "topic_options": topic_options}

    def _resolve_topic(self, params):
        file_path = params.get("file_path", "")
        topic = params.get("topic", "").strip()
        if not file_path or not topic:
            return {"success": False, "message": "参数缺失"}

        from sidecar.schema_validator import require_topic

        ok, err = require_topic(topic)
        if not ok:
            return {"success": False, "message": err}

        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)
        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}

        result = write_topic_to_file(str(full_path), topic)
        if not result.get("success"):
            return result

        move_file_to_notes_topic_folder(str(full_path), topic)
        self._sync_wiki_with_folder_system()

        pending = load_pending()
        workspace = config.workspace_path
        try:
            rel_path = str(full_path.relative_to(workspace)) if full_path.is_relative_to(workspace) else str(full_path)
        except ValueError:
            rel_path = str(full_path)
        pending = [p for p in pending if p.get("file") != rel_path]
        save_pending(pending)

        self._start_task(f"cascade_{topic}_{full_path.stem}", self._do_cascade_survey_update, args=(topic,))

        return {"success": True, "message": f"已确认主题「{topic}」"}

    def _get_activity_log(self, params):
        limit = params.get("limit", 50)
        return {"entries": get_entries(limit)}

    def _merge_duplicate_topics(self, _params):
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

    def _get_survey_status(self, _params):
        surveys = get_survey_status()
        return {"success": True, "surveys": surveys}

    def _toggle_survey(self, params):
        topic_name = params.get("topic", "").strip()
        if not topic_name:
            return {"success": False, "message": "未指定主题"}
        return toggle_survey(topic_name)
