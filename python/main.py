import sys
import json
import asyncio
import threading
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config import config, is_ignored_dir
from modules.web_downloader import WebDownloader
from modules.file_converter import FileConverterManager
from modules.file_preview import FilePreviewer
from modules.note_integration import NoteIntegration
from modules.topic_extractor import TopicExtractor
from utils.helpers import call_llm, check_api_config, test_api_connection
from utils.tag_extractor import extract_tags_from_filename, add_yaml_frontmatter_to_file


class SidecarServer:
    def __init__(self):
        self.web_downloader = WebDownloader()
        self.file_converter = FileConverterManager()
        self.file_previewer = FilePreviewer()
        self.note_integration = None
        self.topic_extractor = TopicExtractor()
        self._progress_callback = None
        self._running_tasks = set()
        self._stdout_lock = threading.Lock()

    def _send_response(self, resp):
        with self._stdout_lock:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + '\n')
            sys.stdout.flush()

    def _send_progress(self, element_id, progress, message):
        self._send_response({
            "id": "event",
            "result": {
                "type": "progress",
                "element_id": element_id,
                "progress": progress,
                "message": message
            }
        })

    def _start_task(self, task_name, target, args=(), kwargs=None):
        if task_name in self._running_tasks:
            return False
        self._running_tasks.add(task_name)

        def _wrapped():
            try:
                target(*args, **(kwargs or {}))
            finally:
                self._running_tasks.discard(task_name)

        threading.Thread(target=_wrapped, daemon=True).start()
        return True

    def handle_request(self, request):
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id", "")

        handler_map = {
            "get_api_config": self._get_api_config,
            "save_api_config": self._save_api_config,
            "get_ui_config": self._get_ui_config,
            "save_ui_config": self._save_ui_config,
            "get_theme_preference": self._get_theme_preference,
            "save_theme_preference": self._save_theme_preference,
            "get_workspace_status": self._get_workspace_status,
            "check_workspace_path_valid": self._check_workspace_path_valid,
            "clear_saved_workspace": self._clear_saved_workspace,
            "set_workspace_path": self._set_workspace_path,
            "start_web_download": self._start_web_download,
            "import_files": self._import_files,
            "reveal_in_finder": self._reveal_in_finder,
            "delete_file": self._delete_file,
            "start_file_conversion": self._start_file_conversion,
            "extract_topics": self._extract_topics,
            "start_note_integration": self._start_note_integration,
            "get_file_preview": self._get_file_preview,
            "can_preview_file": self._can_preview_file,
            "save_file_content": self._save_file_content,
            "get_workspace_tree": self._get_workspace_tree,
            "get_all_tags": self._get_all_tags,
            "get_topic_tree": self._get_topic_tree,
            "auto_tag_files": self._auto_tag_files,
            "save_tags_md": self._save_tags_md,
            "auto_assign_topic": self._auto_assign_topic,
            "batch_auto_assign_topics": self._batch_auto_assign_topics,
            "get_pending_topics": self._get_pending_topics,
            "resolve_topic": self._resolve_topic,
            "rename_topic": self._rename_topic,
            "move_file_to_topic": self._move_file_to_topic,
            "test_api_connection": self._test_api_connection,
            "on_file_selected": self._on_file_selected,
            "refresh_log": self._refresh_log,
        }

        handler = handler_map.get(method)
        if handler:
            try:
                result = handler(params)
                self._send_response({"id": req_id, "result": result})
            except Exception as e:
                import traceback
                sys.stderr.write(f"[ERROR] Handler exception: {e}\n")
                sys.stderr.write(traceback.format_exc())
                sys.stderr.flush()
                self._send_response({"id": req_id, "error": str(e)})
        else:
            sys.stderr.write(f"[ERROR] Unknown method: {method}\n")
            sys.stderr.flush()
            self._send_response({"id": req_id, "error": f"Unknown method: {method}"})

    def _get_api_config(self, params):
        api_key = config.api_key or ""
        if len(api_key) > 12:
            masked = api_key[:4] + "■■■■" + api_key[-4:]
        elif api_key:
            masked = "■■■■"
        else:
            masked = ""
        return {
            "api_key": masked,
            "api_key_configured": bool(config.api_key),
            "api_base": config.api_base,
            "model_name": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "max_context_tokens": config.max_context_tokens,
        }

    def _save_api_config(self, params):
        api_key = params.get("api_key", "")
        api_base = params.get("api_base", "https://api.openai.com/v1")
        model_name = params.get("model_name", "gpt-4")

        if "■■■■" in api_key:
            api_key = config.api_key

        if not api_key or not api_key.strip():
            return {"success": False, "message": "API Key 不能为空"}

        from utils.helpers import test_api_connection
        connected, conn_msg = test_api_connection(api_key, api_base, model_name)
        if not connected:
            return {"success": False, "message": conn_msg}

        config.api_key = api_key
        config.api_base = api_base
        config.model_name = model_name
        config.temperature = params.get("temperature", 0.7)
        config.max_tokens = params.get("max_tokens", 32000)
        config.max_context_tokens = params.get("max_context_tokens", 128000)

        save_ok, save_msg = config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True, "message": f"配置已保存，{conn_msg}"}

    def _get_ui_config(self, params):
        return {
            "web_ai_assist": config.web_ai_assist,
            "web_include_images": config.web_include_images,
            "conv_ai_assist": config.conv_ai_assist,
            "integration_strategy": config.integration_strategy,
            "auto_topic": config.auto_topic,
            "topic_list": config.topic_list,
        }

    def _save_ui_config(self, params):
        if "web_ai_assist" in params:
            config.web_ai_assist = params["web_ai_assist"]
        if "web_include_images" in params:
            config.web_include_images = params["web_include_images"]
        if "conv_ai_assist" in params:
            config.conv_ai_assist = params["conv_ai_assist"]
        if "integration_strategy" in params:
            config.integration_strategy = params["integration_strategy"]
        if "auto_topic" in params:
            config.auto_topic = params["auto_topic"]
        if "topic_list" in params:
            config.topic_list = params["topic_list"]
        save_ok, save_msg = config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True, "message": "UI 配置已保存"}

    def _get_theme_preference(self, params):
        return config.theme_preference

    def _save_theme_preference(self, params):
        config.theme_preference = params.get("theme", "system")
        save_ok, save_msg = config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True}

    def _get_workspace_status(self, params):
        path = config.workspace_path
        if path and Path(path).exists():
            self.file_previewer.workspace_path = path
            return {
                "is_set": True,
                "workspace_path": path,
                "notes_folder": str(Path(path) / "Notes"),
                "organized_folder": str(Path(path) / "Organized"),
                "saved_workspace": True,
            }
        return {"is_set": False, "saved_workspace": False}

    def _check_workspace_path_valid(self, params):
        path = params.get("path", config.workspace_path)
        if path and Path(path).exists():
            return {"is_valid": True, "message": "工作区路径有效", "path": path}
        return {"is_valid": False, "message": "工作区路径无效", "path": path}

    def _clear_saved_workspace(self, params):
        from config.settings import WorkspaceStateManager
        WorkspaceStateManager.clear()
        config.workspace_path = ""
        save_ok, save_msg = config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True, "message": "已清除保存的工作区"}

    def _set_workspace_path(self, params):
        path = params.get("path", "")
        if path and Path(path).exists():
            config.workspace_path = path
            save_ok, save_msg = config.save()
            if not save_ok:
                return {"success": False, "message": save_msg}
            self.file_previewer.workspace_path = path
            return {"success": True, "message": "工作区已设置", "workspace_path": path}
        return {"success": False, "message": "路径无效"}

    def _start_web_download(self, params):
        urls = params.get("urls", [])
        ai_assist = params.get("ai_assist", False)
        include_images = params.get("include_images", True)
        save_path = config.workspace_path
        if not save_path:
            return {"success": False, "message": "请先设置工作区"}
        if not urls:
            return {"success": False, "message": "请输入至少一个URL"}

        if not self._start_task("web_download", self._do_web_download, args=(urls, save_path, ai_assist, include_images)):
            return {"success": False, "message": "下载任务正在进行中，请稍后"}

        return {"success": True, "message": "下载已开始"}

    def _do_web_download(self, urls, save_path, ai_assist, include_images):
        try:
            def progress_cb(current, total, message):
                self._send_progress("web-progress", current / total if total > 0 else 0, message)

            self.web_downloader.progress_callback = progress_cb
            self.web_downloader.ai_assist = ai_assist
            self.web_downloader.include_images = include_images
            result = self.web_downloader.download_batch(urls, save_path)
            success_count = sum(1 for r in result if r.get("success"))
            self._send_response({
                "id": "event",
                "result": {"type": "web_download_complete", "success_count": success_count, "total": len(result), "data": result}
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] web_download: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "web_download_error", "error": str(e)}
            })

    def _import_files(self, params):
        import shutil
        files = params.get("files", [])
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}
        if not files:
            return {"success": False, "message": "未选择文件"}

        raw_dir = Path(workspace) / "Raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        supported_exts = set(self.file_converter.get_supported_formats())
        copied = []
        skipped = []
        for src in files:
            src_path = Path(src)
            if not src_path.exists():
                skipped.append({"file": src, "reason": "文件不存在"})
                continue
            ext = src_path.suffix.lower()
            if ext not in supported_exts:
                skipped.append({"file": src, "reason": f"不支持的格式: {ext}"})
                continue
            try:
                dst = raw_dir / src_path.name
                if dst.exists():
                    stem = src_path.stem
                    counter = 1
                    while dst.exists():
                        dst = raw_dir / f"{stem}_{counter}{src_path.suffix}"
                        counter += 1
                shutil.copy2(str(src_path), str(dst))
                copied.append(str(dst))
            except Exception as e:
                skipped.append({"file": src, "reason": str(e)})

        if not copied:
            return {"success": False, "message": "没有可导入的文件", "skipped": skipped}

        if not self._start_task("file_import", self._do_file_import, args=(copied, workspace, skipped)):
            return {"success": False, "message": "导入任务正在进行中，请稍后"}

        return {"success": True, "message": "导入已开始", "file_count": len(copied)}

    def _do_file_import(self, copied, workspace, skipped):
        try:
            total = len(copied)
            for i, f in enumerate(copied):
                self._send_progress("import-progress", (i + 1) / total, f"正在转换 {i + 1}/{total}")

            result = self.file_converter.convert_batch(copied, workspace)
            success_count = sum(1 for r in result if r.get("success"))
            fail_count = sum(1 for r in result if not r.get("success"))

            try:
                from utils.tag_extractor import save_tags_md
                if workspace:
                    save_tags_md(workspace)
            except Exception:
                pass

            self._send_response({
                "id": "event",
                "result": {
                    "type": "file_import_complete",
                    "data": {
                        "success": True,
                        "imported": success_count,
                        "failed": fail_count + len(skipped),
                        "skipped": skipped
                    }
                }
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] file_import: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "file_import_error", "error": str(e)}
            })

    def _reveal_in_finder(self, params):
        import subprocess
        import platform
        path = params.get("path", "")
        if not path or not Path(path).exists():
            return {"success": False, "message": "路径不存在"}
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", "-R", path])
            elif platform.system() == "Windows":
                subprocess.Popen(["explorer", "/select,", path])
            else:
                subprocess.Popen(["xdg-open", str(Path(path).parent)])
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _delete_file(self, params):
        import send2trash
        path = params.get("path", "")
        if not path or not Path(path).exists():
            return {"success": False, "message": "路径不存在"}
        try:
            send2trash.send2trash(path)
            return {"success": True}
        except ImportError:
            try:
                if Path(path).is_dir():
                    import shutil
                    shutil.rmtree(path)
                else:
                    Path(path).unlink()
                return {"success": True}
            except Exception as e:
                return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _start_file_conversion(self, params):
        ai_assist = params.get("ai_assist", False)
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        if not self._start_task("file_conversion", self._do_file_conversion, args=(workspace, ai_assist)):
            return {"success": False, "message": "转换任务正在进行中，请稍后"}

        return {"success": True, "message": "转换已开始"}

    def _do_file_conversion(self, workspace, ai_assist):
        try:
            result = self.file_converter.convert_folder(
                workspace, ai_assist=ai_assist
            )
            self._send_response({
                "id": "event",
                "result": {"type": "file_conversion_complete", "data": result}
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] file_conversion: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "file_conversion_error", "error": str(e)}
            })

    def _extract_topics(self, params):
        topic_count = params.get("topic_count", None)
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        result = self.topic_extractor.extract_topics(
            workspace, topic_count=topic_count
        )
        if not result.get("success"):
            return {"success": False, "message": result.get("error", "提取主题失败")}
        return result

    def _start_note_integration(self, params):
        auto_topic = params.get("auto_topic", True)
        topics = params.get("topics", [])
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        self.note_integration = NoteIntegration(workspace)

        if not self._start_task("note_integration", self._do_note_integration, args=(auto_topic, topics)):
            return {"success": False, "message": "整合任务正在进行中，请稍后"}

        return {"success": True, "message": "整合已开始"}

    def _do_note_integration(self, auto_topic, topics):
        try:
            result = self.note_integration.integrate(
                auto_topic=auto_topic,
                topics=topics
            )
            self._send_response({
                "id": "event",
                "result": {"type": "note_integration_complete", "data": result}
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] note_integration: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "note_integration_error", "error": str(e)}
            })

    def _get_file_preview(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        result = self.file_previewer.get_preview_data(full_path)
        return result

    def _can_preview_file(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        return self.file_previewer.can_preview(full_path)

    def _save_file_content(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        try:
            Path(full_path).write_text(params.get("content", ""), encoding="utf-8")
            return {"success": True, "message": "文件已保存"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _on_file_selected(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        return {"success": True, "path": full_path}

    def _refresh_log(self, params):
        return {"success": True, "message": "日志已刷新"}

    def _resolve_path(self, path):
        if not path:
            return path
        if Path(path).is_absolute():
            return path
        workspace = config.workspace_path
        if workspace:
            return str(Path(workspace) / path)
        return path

    def _get_workspace_tree(self, params):
        workspace = config.workspace_path
        if not workspace:
            return []

        def _build_tree(path, prefix=""):
            items = []
            try:
                entries = sorted(Path(path).iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                for entry in entries:
                    if entry.name.startswith('.'):
                        continue
                    rel = str(entry.relative_to(workspace))
                    if entry.is_dir():
                        children = _build_tree(str(entry), rel)
                        items.append({
                            "name": entry.name,
                            "path": rel,
                            "type": "folder",
                            "children": children,
                        })
                    else:
                        stat = entry.stat()
                        items.append({
                            "name": entry.name,
                            "path": rel,
                            "type": "file",
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                        })
            except PermissionError:
                pass
            return items

        return _build_tree(workspace)

    def _get_all_tags(self, params):
        workspace = config.workspace_path
        if not workspace:
            return {"tags": []}

        import re
        tag_map = {}

        def _scan_dir(path):
            try:
                for entry in sorted(Path(path).iterdir(), key=lambda p: p.name.lower()):
                    if entry.name.startswith('.'):
                        continue
                    if entry.is_dir():
                        if is_ignored_dir(entry.name):
                            continue
                        _scan_dir(str(entry))
                    elif entry.suffix.lower() == '.md':
                        try:
                            text = entry.read_text(encoding='utf-8')
                            m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
                            if not m:
                                continue
                            yaml_text = m.group(1)
                            rel = str(entry.relative_to(workspace))
                            current_tags_key = False
                            current_tags_arr = []
                            for line in yaml_text.split('\n'):
                                stripped = line.strip()
                                if current_tags_key and stripped.startswith('- '):
                                    current_tags_arr.append(stripped[2:].strip().strip("'\""))
                                    continue
                                if current_tags_key and current_tags_arr:
                                    for tag in current_tags_arr:
                                        if tag not in tag_map:
                                            tag_map[tag] = []
                                        tag_map[tag].append(rel)
                                    current_tags_key = False
                                    current_tags_arr = []
                                idx = line.find(':')
                                if idx < 0:
                                    continue
                                key = line[:idx].strip()
                                val = line[idx + 1:].strip()
                                if key != 'tags':
                                    current_tags_key = False
                                    continue
                                if val.startswith('[') and val.endswith(']'):
                                    tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
                                    for tag in tags:
                                        if tag not in tag_map:
                                            tag_map[tag] = []
                                        tag_map[tag].append(rel)
                                    current_tags_key = False
                                elif not val:
                                    current_tags_key = True
                                    current_tags_arr = []
                                else:
                                    tag = val.strip().strip("'\"")
                                    if tag:
                                        if tag not in tag_map:
                                            tag_map[tag] = []
                                        tag_map[tag].append(rel)
                                    current_tags_key = False
                            if current_tags_key and current_tags_arr:
                                for tag in current_tags_arr:
                                    if tag not in tag_map:
                                        tag_map[tag] = []
                                    tag_map[tag].append(rel)
                        except Exception as e:
                            sys.stderr.write(f"[get_all_tags] error reading {entry}: {e}\n")
                            sys.stderr.flush()
            except PermissionError:
                pass

        _scan_dir(workspace)

        sorted_tags = sorted(tag_map.items(), key=lambda x: -len(x[1]))
        return {"tags": [{"name": t, "count": len(f), "files": f} for t, f in sorted_tags]}

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

        return {"topics": topics, "pending": pending}

    def _auto_tag_files(self, params):
        import re
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        tag_map = {}
        for entry in Path(workspace).iterdir():
            if not entry.is_dir() or entry.name.startswith('.'):
                continue
            if is_ignored_dir(entry.name):
                continue
            for md_file in entry.glob('*.md'):
                try:
                    text = md_file.read_text(encoding='utf-8')
                    m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
                    if not m:
                        continue
                    yaml_text = m.group(1)
                    for line in yaml_text.split('\n'):
                        idx = line.find(':')
                        if idx < 0:
                            continue
                        key = line[:idx].strip()
                        val = line[idx + 1:].strip()
                        if key != 'tags':
                            continue
                        if val.startswith('[') and val.endswith(']'):
                            tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
                        else:
                            continue
                        for tag in tags:
                            if tag not in tag_map:
                                tag_map[tag] = []
                except Exception:
                    pass

        if not tag_map:
            return {"success": True, "updated": 0, "message": "未找到已有标签"}

        all_tag_names = list(tag_map.keys())
        updated = 0

        for entry in Path(workspace).iterdir():
            if not entry.is_dir() or entry.name.startswith('.'):
                continue
            if is_ignored_dir(entry.name):
                continue
            for md_file in entry.glob('*.md'):
                try:
                    text = md_file.read_text(encoding='utf-8')
                    fname = md_file.stem
                    matched_tags = [t for t in all_tag_names if t.lower() in fname.lower()]
                    if not matched_tags:
                        continue

                    m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', text.lstrip('\ufeff'))
                    if m:
                        yaml_text = m.group(2)
                        existing_tags = set()
                        tags_line_idx = None
                        tags_line = None
                        lines = yaml_text.split('\n')
                        for i, line in enumerate(lines):
                            idx = line.find(':')
                            if idx < 0:
                                continue
                            key = line[:idx].strip()
                            val = line[idx + 1:].strip()
                            if key == 'tags':
                                tags_line_idx = i
                                tags_line = line
                                if val.startswith('[') and val.endswith(']'):
                                    existing_tags = set(t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip())
                                break

                        new_tags = [t for t in matched_tags if t not in existing_tags]
                        if not new_tags:
                            continue

                        all_tags = list(existing_tags) + new_tags
                        new_tags_str = '[' + ', '.join(all_tags) + ']'

                        if tags_line_idx is not None:
                            lines[tags_line_idx] = 'tags: ' + new_tags_str
                            new_yaml = '\n'.join(lines)
                            new_text = '\ufeff' + m.group(1) + new_yaml + m.group(3) + text.lstrip('\ufeff')[m.end():]
                        else:
                            new_yaml = yaml_text + '\ntags: ' + new_tags_str
                            new_text = '\ufeff' + m.group(1) + new_yaml + m.group(3) + text.lstrip('\ufeff')[m.end():]

                        md_file.write_text(new_text, encoding='utf-8')
                        updated += 1
                    else:
                        new_tags_str = '[' + ', '.join(matched_tags) + ']'
                        frontmatter = '---\ntags: ' + new_tags_str + '\n---\n'
                        new_text = frontmatter + text
                        md_file.write_text(new_text, encoding='utf-8')
                        updated += 1
                except Exception as e:
                    sys.stderr.write(f"[auto_tag] error processing {md_file}: {e}\n")
                    sys.stderr.flush()

        return {"success": True, "updated": updated}

    def _save_tags_md(self, params):
        from utils.tag_extractor import save_tags_md
        return save_tags_md(config.workspace_path)

    def _get_pending_topics_path(self):
        workspace = config.workspace_path
        if not workspace:
            return None
        return Path(workspace) / ".pending_topics.json"

    def _load_pending_topics(self):
        path = self._get_pending_topics_path()
        if not path or not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return []

    def _save_pending_topics(self, pending):
        path = self._get_pending_topics_path()
        if not path:
            return
        path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding='utf-8')

    def _parse_wiki_headings(self):
        workspace = config.workspace_path
        if not workspace:
            return []
        wiki_path = Path(workspace) / "WIKI.md"
        if not wiki_path.exists():
            return []
        try:
            text = wiki_path.read_text(encoding='utf-8')
        except Exception:
            return []

        headings = []
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped.startswith('## ') and not stripped.startswith('### '):
                headings.append({"level": 2, "name": stripped[3:].strip()})
            elif stripped.startswith('### '):
                headings.append({"level": 3, "name": stripped[4:].strip()})
        return headings

    def _auto_assign_topic(self, params):
        from utils.topic_assigner import auto_assign_topic_for_file, load_pending, parse_wiki_headings, write_topic_to_file
        file_path = params.get("file_path", "")
        if not file_path:
            return {"success": False, "message": "未指定文件"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        full_path = Path(workspace) / file_path if not Path(file_path).is_absolute() else Path(file_path)
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
                if is_ignored_dir(str(md_file)):
                    continue
                md_files.append(md_file)

        save_pending([])

        files_to_process = 0
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

            auto_assign_topic_for_file(str(md_file))
            files_to_process += 1

        pending = load_pending()
        need_confirm = len(pending)
        auto_assigned = files_to_process - need_confirm

        return {
            "success": True,
            "total": len(md_files),
            "auto_assigned": auto_assigned,
            "need_confirm": need_confirm,
            "skipped": skipped,
            "pending": pending
        }

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

        full_path = Path(workspace) / file_path if not Path(file_path).is_absolute() else Path(file_path)
        write_topic_to_file(str(full_path), topic)

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

    def _move_file_to_topic(self, params):
        from utils.topic_assigner import move_file_to_topic
        file_path = params.get("file_path", "")
        new_topic = params.get("new_topic", "")
        if not file_path or not new_topic:
            return {"success": False, "message": "参数不完整"}

        return move_file_to_topic(file_path, new_topic)

    def _test_api_connection(self, params):
        try:
            api_key = params.get("api_key", config.api_key or "")
            api_base = params.get("api_base", config.api_base or "https://api.openai.com/v1")
            model_name = params.get("model_name", config.model_name or "gpt-4")
            if "■■■■" in api_key:
                api_key = config.api_key
            connected, conn_msg = test_api_connection(api_key, api_base, model_name)
            if connected:
                return {"success": True, "message": conn_msg}
            else:
                return {"success": False, "message": conn_msg}
        except Exception as e:
            return {"success": False, "message": str(e)}


def main():
    server = SidecarServer()
    sys.stderr.write("[Python Sidecar] Ready\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            server.handle_request(request)
        except json.JSONDecodeError as e:
            server._send_response({"id": "", "error": f"Invalid JSON: {e}"})
        except Exception as e:
            server._send_response({"id": "", "error": str(e)})


if __name__ == "__main__":
    main()
