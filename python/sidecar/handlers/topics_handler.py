import json
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from config import config, is_ignored_dir
from config.constants import TOPIC_SEP, WORKSPACE_APP_FOLDER
from sidecar.cascade import (
    append_changelog,
    cascade_on_topic_resolved,
    ensure_topic_folder,
)
from sidecar.handlers.base import BaseHandler
from sidecar.mixins.topics_3tier_mixin import Topics3TierMixin
from sidecar.wiki_utils import (
    create_topic as wiki_create_topic,
)
from sidecar.wiki_utils import (
    get_survey_status,
    parse_wiki_headings,
    read_wiki_text,
    sync_wiki_with_files,
    toggle_survey,
)
from utils.activity_log import get_entries
from utils.logger import logger
from utils.text_utils import parse_frontmatter
from utils.topic_assigner import (
    auto_assign_topic_for_file,
    load_pending,
    move_file_to_notes_topic_folder,
    save_pending,
    write_topic_to_file,
)
from utils.topic_dedup import (
    _deduplicate_files_in_wiki,
    _merge_duplicate_topics_in_wiki,
)
from utils.topic_manager import TopicManager

_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+)$")
_META_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)


def _parse_heading_comment(comment: str) -> dict:
    """解析段头注释内容，兼容 JSON 对象与 `key: value` 行两种格式。"""
    body = comment.strip()
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            return data
    except (TypeError, ValueError):
        pass
    result: dict = {}
    for line in body.splitlines():
        key, sep, value = line.strip().partition(":")
        if sep and key.strip():
            result[key.strip()] = value.strip()
    return result


def parse_topic_wiki_meta(topic: str) -> dict | None:
    """读取 WIKI.md 中指定主题段头的 HTML 注释元数据。

    Returns:
        dict —— 主题段存在（元数据可能为空字典）；None —— WIKI.md 不存在或主题段不存在。
    """
    text = read_wiki_text()
    if text is None:
        return None
    topic_stack: list[str] = []
    found = False
    section_lines: list[str] = []
    comment_balance = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "<!-- NOTEAI_TAGS_START -->":
            break
        match = _HEADING_RE.match(stripped)
        if match:
            if found:
                break
            label = match.group(2).strip()
            if label in ("目录", "来源文件"):
                continue
            level = len(match.group(1)) - 1
            while len(topic_stack) >= level:
                topic_stack.pop()
            parent = topic_stack[-1] if topic_stack else ""
            full = f"{parent}{TOPIC_SEP}{label}" if parent else label
            topic_stack.append(full)
            if full == topic:
                found = True
                section_lines = []
                comment_balance = 0
            continue
        if found:
            section_lines.append(line)
            comment_balance += stripped.count("<!--") - stripped.count("-->")
            if comment_balance <= 0 and stripped and not stripped.startswith("<!--") and "-->" not in stripped:
                break
    if not found:
        return None
    meta: dict = {}
    for m in _META_COMMENT_RE.finditer("\n".join(section_lines)):
        meta.update(_parse_heading_comment(m.group(1)))
    return meta


def _read_topic_state(workspace: str, topic: str) -> dict | None:
    """读取主题的语义编译状态文件（topic_states/{topic_id}.json），不存在时返回 None。"""
    from sidecar.semantic.ids import stable_id

    topic_id = stable_id("top", topic.casefold())
    state_path = Path(workspace) / WORKSPACE_APP_FOLDER / "compiler" / "topic_states" / f"{topic_id}.json"
    if not state_path.is_file():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _parse_iso_timestamp(value) -> float | None:
    """将 ISO 时间字符串转为 epoch 秒，失败返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _latest_note_mtime(topic: str, workspace: str) -> float | None:
    """主题下源笔记的最新 mtime（复用 get_survey_overview 同款 collect_topic_notes 判定）。"""
    from sidecar.cascade import collect_topic_notes

    ws = Path(workspace)
    mtimes: list[float] = []
    for note in collect_topic_notes(topic, include_content=False):
        note_path = ws / note["file_path"]
        try:
            mtimes.append(note_path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes) if mtimes else None


def _note_matches_topic(
    file_topic: str, file_topics: list, rel_parts: tuple, topic: str, topic_parts: list[str]
) -> bool:
    """单篇笔记是否归属指定主题：判定标准与 cascade.collect_topic_notes 完全一致
    （frontmatter topic/前缀、frontmatter topics 列表、Notes 目录路径前缀）。"""
    if file_topic and (
        file_topic == topic
        or topic_parts
        and file_topic.startswith(topic + TOPIC_SEP)
        or len(topic_parts) == 1
        and (file_topic == topic_parts[0] or file_topic.startswith(topic_parts[0] + TOPIC_SEP))
    ):
        return True
    if isinstance(file_topics, list) and topic in file_topics:
        return True
    if topic_parts and rel_parts and rel_parts[0] == topic_parts[0]:
        if len(topic_parts) == 1:
            return True
        if len(rel_parts) >= 2 and rel_parts[1] == topic_parts[1]:
            if len(topic_parts) == 2 or len(rel_parts) >= 3 and rel_parts[2] == topic_parts[2]:
                return True
    return False


def _topic_conflict_pending_count(workspace: str, topic: str) -> int:
    """该主题未裁决的 claim_conflict 数（同 semantic_handler overview 的 review_queue 查询）。"""
    import sqlite3

    db_path = Path(workspace) / WORKSPACE_APP_FOLDER / "compiler" / "semantic.db"
    if not db_path.is_file():
        return 0
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return 0
    try:
        row = conn.execute(
            """SELECT count(DISTINCT rq.id) AS cnt FROM review_queue rq
               JOIN claims c ON c.id IN (
                   json_extract(rq.payload_json, '$.claim_a_id'),
                   json_extract(rq.payload_json, '$.claim_b_id'))
               JOIN evidence e ON e.claim_id = c.id AND e.status = 'active'
               JOIN blocks b ON b.id = e.block_id
               JOIN documents d ON d.id = b.document_id
               WHERE rq.item_kind = 'claim_conflict' AND rq.status = 'pending'
                 AND (d.topic = ? OR instr(d.topic, ?) = 1)""",
            (topic, topic + " > "),
        ).fetchone()
        return int(row["cnt"]) if row else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


class TopicsHandler(BaseHandler, Topics3TierMixin):
    _pending_maintenance_schedule_lock = threading.Lock()
    _pending_maintenance_last_scheduled: dict[str, float] = {}
    _pending_maintenance_interval_seconds = 30.0

    def _sync_wiki_with_folder_system(self, _params=None):
        try:
            return sync_wiki_with_files()
        except Exception as e:
            logger.warning(f"[topics_handler] sync WIKI with folder system failed: {e}\n")
            return {"success": False, "message": str(e)}

    def _topic_dir_path(self, workspace_path: Path, topic_name: str) -> Path:
        normalized = topic_name.replace("/", TOPIC_SEP)
        parts = [p.strip() for p in normalized.split(TOPIC_SEP) if p.strip()]
        topic_dir = workspace_path / config.NOTES_FOLDER
        for part in parts:
            topic_dir = topic_dir / part
        return topic_dir

    def _topic_artifact_dir_path(self, workspace_path: Path, root_folder: str, topic_name: str) -> Path:
        normalized = topic_name.replace("/", TOPIC_SEP)
        parts = [p.strip() for p in normalized.split(TOPIC_SEP) if p.strip()]
        topic_dir = workspace_path / root_folder
        for part in parts:
            topic_dir = topic_dir / part
        return topic_dir

    def _get_topic_tree(self, params):
        return self._get_topic_tree_3tier(params)

    def _get_topic_tree_3tier(self, params):
        """三层主题树 + stale_topics（仅新增字段，既有结构不变）。"""
        result = super()._get_topic_tree_3tier(params)
        stale: list[str] = []
        workspace = config.workspace_path
        if workspace:
            try:
                stale = self._collect_stale_topics(workspace)
            except Exception as e:
                logger.warning(f"[topics_handler] stale topics scan failed: {e}\n")
        result["stale_topics"] = stale
        return result

    def _collect_stale_topics(self, workspace: str) -> list[str]:
        """轻量 stale 扫描：仅检查已有 topic_states 的主题，判定逻辑与 get_survey_overview 一致。

        单次全库遍历：一次 rglob + 逐文件头部 frontmatter 解析，按候选主题聚合
        最新 mtime，避免逐主题调用 collect_topic_notes 造成 O(主题数×全库文件数)。
        """
        states_dir = Path(workspace) / WORKSPACE_APP_FOLDER / "compiler" / "topic_states"
        if not states_dir.is_dir():
            return []
        candidates: list[tuple[str, float]] = []
        for state_file in sorted(states_dir.glob("*.json")):
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            topic = data.get("topic")
            compiled_ts = _parse_iso_timestamp(data.get("generated_at"))
            if not topic or compiled_ts is None:
                continue
            candidates.append((str(topic), compiled_ts))
        if not candidates:
            return []

        ws = Path(workspace)
        notes_dir = ws / config.NOTES_FOLDER
        notes_dir_exists = notes_dir.exists()
        topic_parts_cache: dict[str, list[str]] = {}
        latest_mtime: dict[str, float] = {}
        for md_file in ws.rglob("*.md"):
            if md_file.name.startswith("."):
                continue
            if "wiki" in md_file.parts:
                continue
            if md_file.name.endswith("_综述.md") or md_file.name.endswith("综述.md"):
                continue
            try:
                # 只读文件头部解析 frontmatter（同 collect_topic_notes 轻量模式），大文件不读全文
                with md_file.open("r", encoding="utf-8") as fh:
                    text = fh.read(8192)
                fm, _body = parse_frontmatter(text)
            except Exception:
                continue
            file_topic = ""
            file_topics: list = []
            if fm:
                ft = fm.get("topic", "")
                if isinstance(ft, str):
                    file_topic = ft
                fts = fm.get("topics", [])
                if isinstance(fts, list):
                    file_topics = fts
            rel_parts: tuple = ()
            if notes_dir_exists:
                try:
                    rel_parts = md_file.relative_to(notes_dir).parts
                except ValueError:
                    rel_parts = ()
            try:
                mtime = md_file.stat().st_mtime
            except OSError:
                continue
            for topic, _compiled_ts in candidates:
                parts = topic_parts_cache.get(topic)
                if parts is None:
                    parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
                    topic_parts_cache[topic] = parts
                if _note_matches_topic(file_topic, file_topics, rel_parts, topic, parts):
                    if mtime > latest_mtime.get(topic, float("-inf")):
                        latest_mtime[topic] = mtime

        stale: list[str] = []
        for topic, compiled_ts in candidates:
            latest = latest_mtime.get(topic)
            if latest is not None and latest > compiled_ts:
                stale.append(topic)
        return stale

    def _topic_meta(self, params):
        """主题可信度元数据（只读）：来源数/冲突待处理数/编译时间/是否过期。"""
        topic = str(params.get("topic") or "").strip()
        if not topic:
            return {"success": False, "message": "未指定主题"}
        workspace, err = self._require_workspace()
        if err:
            return err
        try:
            wiki_meta = parse_topic_wiki_meta(topic)
        except Exception as e:
            logger.warning(f"[topics_handler] parse wiki meta failed: {e}\n")
            wiki_meta = None
        state = _read_topic_state(workspace, topic)
        if wiki_meta is None and state is None:
            try:
                latest = _latest_note_mtime(topic, workspace)
            except Exception:
                latest = None
            if latest is None:
                return {"exists": False}
        wiki_meta = wiki_meta or {}
        stats = state.get("stats") if state else None
        stats_documents = stats.get("documents") if isinstance(stats, dict) else None
        try:
            source_count = int(
                stats_documents if isinstance(stats_documents, int) else wiki_meta.get("source_count", 0)
            )
        except (TypeError, ValueError):
            source_count = 0
        try:
            conflict_count = int(wiki_meta.get("conflict_pending_count", 0))
        except (TypeError, ValueError):
            conflict_count = 0
        if conflict_count == 0:
            try:
                conflict_count = _topic_conflict_pending_count(workspace, topic)
            except Exception:
                conflict_count = 0
        compiled_at = state.get("generated_at") if state else None
        is_stale = False
        try:
            latest_mtime = _latest_note_mtime(topic, workspace)
        except Exception:
            latest_mtime = None
        if latest_mtime is not None:
            compiled_ts = _parse_iso_timestamp(compiled_at)
            is_stale = compiled_ts is None or latest_mtime > compiled_ts
        return {
            "exists": True,
            "source_count": source_count,
            "conflict_pending_count": conflict_count,
            "compiled_at": compiled_at,
            "is_stale": is_stale,
        }

    def _parse_wiki_headings(self):
        return parse_wiki_headings()

    def _batch_auto_assign_topics(self, _params):
        if not config.workspace_path:
            return {"success": False, "message": "未设置工作区或工作区不存在"}

        from sidecar.workspace_meta import is_inbox_orphan_path

        ws = Path(config.workspace_path)
        md_files = [
            f
            for f in ws.rglob("*.md")
            if not f.name.startswith(".")
            and "wiki" not in f.parts
            and not is_ignored_dir(f.parent.name)
            and is_inbox_orphan_path(f)
        ]
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
                logger.error(f"[topics_handler] batch assign error {md_file}: {e}")
                skipped += 1

            if i % 10 == 0:
                self._send_progress("topic-assign-progress", int((i + 1) / total * 100), f"处理中 {i + 1}/{total}")

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
        from sidecar.workspace_rules_validator import require_topic

        ok, err = require_topic(topic)
        if not ok:
            return {"success": False, "message": err}
        try:
            write_result = write_topic_to_file(str(full_path), topic)
            if not write_result.get("success"):
                return write_result
            move_result = move_file_to_notes_topic_folder(str(full_path), topic)
            if not move_result.get("success"):
                return move_result
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

        from sidecar.workspace_rules_validator import require_topic

        ok, err = require_topic(topic_full)
        if not ok:
            return {"success": False, "message": err}

        workspace, err = self._require_workspace()
        if err:
            return err

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
        workspace, err = self._require_workspace()
        if err:
            return err

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
        workspace, err = self._require_workspace()
        if err:
            return err

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
                logger.error(f"[delete_topic] rmdir: {e}")

        org_dir = self._topic_artifact_dir_path(workspace_path, config.ABSTRACT_FOLDER, topic_name)
        if org_dir.exists():
            try:
                shutil.rmtree(str(org_dir))
            except Exception as e:
                logger.error(f"[delete_topic] rmdir org: {e}")

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

    def _do_cascade_survey_update(self, topic):
        from sidecar.cascade_runner import run_cascade_survey_update

        run_cascade_survey_update(topic, send_response=self._send_response)

    def _do_file_added_cascade(self, file_path: Path):
        try:
            text = file_path.read_text(encoding="utf-8")
            fm, _ = self._parse_frontmatter(text)
            topic = fm.get("topic") if fm else None
            if topic:
                self._start_task(
                    f"cascade_{topic}_{file_path.stem}", cascade_on_topic_resolved, args=(str(file_path), topic)
                )
        except Exception as e:
            logger.error(f"[topics_handler] file_added_cascade error: {e}")

    def _get_all_pending(self, _params):
        workspace = config.workspace_path
        topic_options: list[str] = []
        maintenance_started = self.schedule_pending_maintenance() if workspace else False
        if workspace:
            try:
                topic_options = TopicManager.collect_topic_labels(workspace)
            except Exception:
                topic_options = []

        from sidecar.pending_items import collect_pending_items

        items = collect_pending_items(workspace)
        summary: dict[str, int] = {}
        for item in items:
            item_type = item.get("type", "other")
            summary[item_type] = summary.get(item_type, 0) + 1
        return {
            "items": items,
            "count": len(items),
            "summary": summary,
            "topic_options": topic_options,
            "auto_moved_count": 0,
            "auto_move_errors": [],
            "maintenance_started": maintenance_started,
        }

    def schedule_pending_maintenance(self) -> bool:
        """Start deduplicated Inbox maintenance without blocking snapshot reads."""
        start_task = getattr(self._server, "_start_task", None)
        if not callable(start_task):
            return False
        workspace = config.workspace_path
        if not workspace:
            return False
        root_key = str(Path(workspace).resolve())
        now = time.monotonic()
        with self._pending_maintenance_schedule_lock:
            elapsed = now - self._pending_maintenance_last_scheduled.get(root_key, float("-inf"))
            if elapsed < self._pending_maintenance_interval_seconds:
                return False
            started = bool(
                start_task(
                    "pending_maintenance",
                    self._run_pending_maintenance,
                    kind="maintenance",
                    label="Inbox maintenance",
                )
            )
            if started:
                self._pending_maintenance_last_scheduled[root_key] = now
            return started

    def _run_pending_maintenance(self) -> None:
        from sidecar.pending_items import run_pending_cleanups_if_due

        workspace = config.workspace_path
        if not workspace:
            return
        cleaned = run_pending_cleanups_if_due(workspace)
        placement = self._apply_topic_placement_threshold({"skip_recent": True})
        if cleaned or placement.get("moved_count") or placement.get("errors"):
            self._send_response(
                {
                    "id": "event",
                    "result": {"type": "workspace_files_changed", "source": "pending_maintenance"},
                }
            )

    def _resolve_topic(self, params):
        file_path = params.get("file_path", "")
        topic = params.get("topic", "").strip()
        if not file_path or not topic:
            return {"success": False, "message": "参数缺失"}

        from sidecar.workspace_rules_validator import require_topic

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

    def _keep_note_in_topic(self, params):
        workspace, err = self._require_workspace()
        if err:
            return err
        try:
            from sidecar.topic_placement import keep_note_in_current_topic

            return keep_note_in_current_topic(
                workspace,
                (params.get("file_path") or "").strip(),
                (params.get("current_topic") or "").strip(),
                (params.get("suggested_topic") or "").strip(),
            )
        except (OSError, ValueError) as exc:
            return {"success": False, "message": str(exc)}

    def _apply_topic_placement_threshold(self, _params):
        workspace, err = self._require_workspace()
        if err:
            return err
        from sidecar.topic_placement import auto_move_misplaced_notes, auto_move_misplaced_notes_if_due

        try:
            if _params.get("skip_recent"):
                result = auto_move_misplaced_notes_if_due(workspace)
            else:
                result = auto_move_misplaced_notes(workspace)
        except Exception as exc:
            logger.exception("[topics_handler] auto topic placement failed")
            return {
                "success": False,
                "message": str(exc),
                "moved": [],
                "moved_count": 0,
                "errors": [{"message": str(exc)}],
            }
        moves = result.get("moved") or []
        affected_topics = {
            str(topic) for move in moves for topic in (move.get("current_topic"), move.get("suggested_topic")) if topic
        }
        for topic in affected_topics:
            self._start_task(f"cascade_topic_move_{topic}", self._do_cascade_survey_update, args=(topic,))
        result["moved_count"] = len(moves)
        return result

    def _suggest_topic_merge_names(self, params):
        workspace, err = self._require_workspace()
        if err:
            return err
        from utils.topic_merge import suggest_merged_topic_names

        return suggest_merged_topic_names(workspace, [str(topic) for topic in (params.get("topics") or [])])

    def _merge_similar_topics(self, params):
        workspace, err = self._require_workspace()
        if err:
            return err
        from utils.topic_merge import merge_topics

        result = merge_topics(
            workspace,
            [str(topic) for topic in (params.get("topics") or [])],
            str(params.get("new_topic") or "").strip(),
        )
        if result.get("success"):
            topic = result.get("new_topic")
            self._start_task(f"cascade_topic_merge_{topic}", self._do_cascade_survey_update, args=(topic,))
        return result

    def _preview_topic_merge(self, params):
        workspace, err = self._require_workspace()
        if err:
            return err
        from utils.topic_merge import preview_topic_merge

        return preview_topic_merge(
            workspace,
            [str(topic) for topic in (params.get("topics") or [])],
            str(params.get("new_topic") or "").strip(),
        )

    def _get_activity_log(self, params):
        limit = params.get("limit", 50)
        return {"entries": get_entries(limit)}

    def _merge_duplicate_topics(self, _params):
        merged = _merge_duplicate_topics_in_wiki()
        deduped = _deduplicate_files_in_wiki()
        return {"success": True, "merged_topics": merged, "deduplicated_files": deduped}

    def register_routes(self, router):
        router.register("get_topic_tree", self._get_topic_tree)
        router.register("topic_meta", self._topic_meta)
        router.register("sync_wiki_with_files", self._sync_wiki_with_folder_system)
        router.register("batch_auto_assign_topics", self._batch_auto_assign_topics)
        router.register("move_file_to_topic", self._move_file_to_topic)
        router.register("create_topic", self._create_topic)
        router.register("rename_topic", self._rename_topic)
        router.register("delete_topic", self._delete_topic)
        router.register("resolve_topic", self._resolve_topic)
        router.register("keep_note_in_topic", self._keep_note_in_topic)
        router.register("apply_topic_placement_threshold", self._apply_topic_placement_threshold)
        router.register("suggest_topic_merge_names", self._suggest_topic_merge_names)
        router.register("merge_similar_topics", self._merge_similar_topics)
        router.register("preview_topic_merge", self._preview_topic_merge)
        router.register("get_all_pending", self._get_all_pending)
        router.register("get_activity_log", self._get_activity_log)
        router.register("merge_duplicate_topics", self._merge_duplicate_topics)
        router.register("get_survey_status", self._get_survey_status)
        router.register("get_survey_overview", self._get_survey_overview)
        router.register("toggle_survey", self._toggle_survey)
        router.register("fix_survey_topics", self._fix_survey_topics)

    def _fix_survey_topics(self, _params):
        try:
            from sidecar.wiki_utils import sync_wiki_with_files

            sync_wiki_with_files()
            return {"success": True, "message": "已同步 wiki 与文件系统"}
        except Exception as e:
            logger.warning(f"[fix_survey_topics] failed: {e}")
            return {"success": False, "message": str(e)}

    def _get_survey_status(self, _params):
        surveys = get_survey_status()
        return {"success": True, "surveys": surveys}

    def _get_survey_overview(self, _params):
        from sidecar.wiki_utils import get_survey_overview

        return {"success": True, "overview": get_survey_overview()}

    def _toggle_survey(self, params):
        topic_name = params.get("topic", "").strip()
        if not topic_name:
            return {"success": False, "message": "未指定主题"}
        return toggle_survey(topic_name)
