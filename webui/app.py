"""
NoteAI HTTP API 服务器

通信机制：
- JS -> Python: 使用 HTTP API (fetch POST /api/method)
- 开发模式下独立运行，生产模式下由 Tauri 通过 python/main.py sidecar 驱动
"""

import sys
import json
import shutil
import re
from pathlib import Path
from urllib.parse import unquote, parse_qs, urlparse

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import config, workspace_manager
from utils.logger import logger
from utils.helpers import APIConfigError, NetworkError
from modules.web_downloader import WebDownloader
from modules.file_converter import FileConverterManager
from modules.note_integration import NoteIntegration
from modules.topic_extractor import TopicExtractor
from modules.file_preview import FilePreviewer
from utils.tag_extractor import tag_files_by_filename


class Api:
    """暴露给 JavaScript 的 API"""

    def __init__(self):
        pass

    def get_workspace_status(self):
        workspace_info = workspace_manager.get_workspace_info()

        return {
            "is_set": config.is_workspace_set(),
            "workspace_path": config.workspace_path,
            "notes_folder": config.get_notes_folder(),
            "organized_folder": config.get_organized_folder(),
            "saved_workspace": {
                "is_saved": workspace_info.get("is_saved", False),
                "is_valid": workspace_info.get("is_valid", False),
                "saved_path": workspace_info.get("saved_path"),
                "workspace_path": workspace_info.get("workspace_path"),
                "workspace_name": workspace_info.get("workspace_name"),
                "last_opened_at": workspace_info.get("last_opened_at"),
                "state_file": workspace_info.get("state_file")
            }
        }

    def check_workspace_path_valid(self):
        if not config.workspace_path:
            return {
                "is_valid": False,
                "message": "工作区路径未设置",
                "path": None
            }

        path = Path(config.workspace_path)
        if not path.exists():
            return {
                "is_valid": False,
                "message": "工作区路径已不存在",
                "path": config.workspace_path
            }

        return {
            "is_valid": True,
            "message": "工作区路径有效",
            "path": config.workspace_path
        }

    def clear_saved_workspace(self):
        success, message = workspace_manager.clear_workspace_state()
        return {
            "success": success,
            "message": message
        }

    def get_api_config(self):
        masked_key = ""
        if config.api_key:
            key = config.api_key.strip()
            if len(key) > 12:
                masked_key = key[:4] + "■■■■" + key[-4:]
            elif key:
                masked_key = "■■■■"
        return {
            "api_key": masked_key,
            "api_key_configured": bool(config.api_key and config.api_key.strip()),
            "api_base": config.api_base,
            "model_name": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "max_context_tokens": config.max_context_tokens
        }

    def _tag_new_files(self, file_paths: list):
        def bg_task():
            try:
                tagged = tag_files_by_filename(file_paths)
                logger.info(f"标签提取完成: {len(tagged)} 个文件")
            except Exception as e:
                logger.warning(f"标签提取失败: {e}")

        import threading
        threading.Thread(target=bg_task, daemon=True).start()

    def start_web_download(self, urls, ai_assist=False, include_images=False):
        import threading
        if not config.is_workspace_set():
            return {"success": False, "message": "请先设置工作文件夹"}

        if not urls:
            return {"success": False, "message": "请输入至少一个URL"}

        if ai_assist and not config.validate_api_config():
            return {"success": False, "message": "AI辅助模式需要配置有效的API Key"}

        save_path = config.get_notes_folder()
        if not save_path:
            return {"success": False, "message": "无法获取Notes文件夹路径"}

        def task():
            try:
                def progress_callback(current, total, message):
                    pass

                downloader = WebDownloader(progress_callback, ai_assist=ai_assist, include_images=include_images)
                results = downloader.download_batch(urls, save_path)

                new_md_files = [r["file_path"] for r in results if r.get("success") and r.get("file_path", "")]
                if new_md_files:
                    self._tag_new_files(new_md_files)
            except Exception as e:
                logger.error(f"下载失败: {e}")

        threading.Thread(target=task, daemon=True).start()
        return {"success": True, "message": "下载已开始"}

    def start_file_conversion(self, ai_assist=False):
        import threading
        if not config.is_workspace_set():
            return {"success": False, "message": "请先设置工作文件夹"}

        if ai_assist and not config.validate_api_config():
            return {"success": False, "message": "AI辅助模式需要配置有效的API Key"}

        save_path = config.get_notes_folder()
        raw_path = config.get_raw_folder()
        workspace_path = config.workspace_path
        if not save_path or not workspace_path:
            return {"success": False, "message": "无法获取工作文件夹路径"}

        def task():
            try:
                def progress_callback(current, total, message):
                    pass

                converter = FileConverterManager(progress_callback)
                results = converter.convert_folder(workspace_path, save_path, raw_path, recursive=True, ai_assist=ai_assist)

                new_md_files = [r.get("output_path") or r.get("file_path") for r in results if r.get("success") and (r.get("output_path") or r.get("file_path"))]
                if new_md_files:
                    self._tag_new_files(new_md_files)
            except Exception as e:
                logger.error(f"转换失败: {e}")

        threading.Thread(target=task, daemon=True).start()
        return {"success": True, "message": "转换已开始"}

    def extract_topics(self, topic_count=None):
        if not config.is_workspace_set():
            return {"success": False, "error": "请先设置工作文件夹"}

        specified_topic_count = None
        if topic_count is not None and topic_count != "":
            try:
                specified_topic_count = int(topic_count)
                if specified_topic_count <= 0:
                    specified_topic_count = None
            except ValueError:
                specified_topic_count = None

        try:
            extractor = TopicExtractor(progress_callback=lambda *a: None)
            result = extractor.extract_topics(specified_topic_count=specified_topic_count)

            if result.get("success"):
                topics = result.get("topics", [])
                logger.info(f"提取了 {len(topics)} 个主题: {topics}")
                return {
                    "success": True,
                    "topics": topics,
                    "topic_count": result.get("topic_count"),
                    "min_topics": result.get("min_topics"),
                    "max_topics": result.get("max_topics"),
                    "is_specified": result.get("is_specified"),
                    "notes_count": result.get("notes_count"),
                    "organized_count": result.get("organized_count")
                }
            else:
                return result

        except Exception as e:
            logger.error(f"提取主题失败: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"提取主题失败: {str(e)}"}

    def start_note_integration(self, auto_topic, topics):
        import threading
        if not config.is_workspace_set():
            return {"success": False, "message": "请先设置工作文件夹"}

        if not topics:
            return {"success": False, "message": "请先提取主题"}

        source_path = config.get_notes_folder()
        output_path = config.get_organized_folder()
        used_path = config.get_used_folder()

        if not source_path or not output_path:
            return {"success": False, "message": "无法获取工作文件夹路径"}

        def task():
            doc_paths = []
            try:
                def progress_callback(current, total, message, max_total=1.0):
                    pass

                Path(output_path).mkdir(parents=True, exist_ok=True)
                Path(used_path).mkdir(parents=True, exist_ok=True)

                integrator = NoteIntegration(progress_callback)
                documents = integrator.load_documents_from_folder(source_path)

                if not documents:
                    return

                doc_paths = [d['path'] for d in documents]
                result = integrator.integrate(documents, output_path, user_topics=topics)

                logger.info(f"整合完成: {result}")

            except Exception as e:
                logger.error(f"整合失败: {e}")
            finally:
                if doc_paths:
                    self._move_docs_to_used(doc_paths, used_path)

        threading.Thread(target=task, daemon=True).start()
        return {"success": True, "message": "整合已开始"}

    def _move_docs_to_used(self, doc_paths, used_path):
        used_dir = Path(used_path)
        if not used_dir.exists():
            return
        for doc_path in doc_paths:
            src = Path(doc_path)
            if not src.exists():
                continue
            dst = used_dir / src.name
            if dst.exists():
                stem = src.stem
                suffix = src.suffix
                counter = 1
                while dst.exists():
                    dst = used_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
            try:
                shutil.move(str(src), str(dst))
            except Exception as e:
                logger.warning(f"移动文件到Used失败 {src}: {e}")

    def save_api_config(self, config_data):
        api_key = config_data.get("api_key", "")
        api_base = config_data.get("api_base", "https://api.openai.com/v1")
        model_name = config_data.get("model_name", "gpt-4")

        logger.info(f"[API配置保存] 开始保存配置...")

        if "■■■■" in api_key:
            logger.info(f"[API配置保存] 检测到掩码，使用已保存的 API Key")
            api_key = config.api_key

        if not api_key or not api_key.strip():
            logger.error("[API配置保存] API Key 为空")
            return {"success": False, "message": "API Key 不能为空"}

        logger.info(f"[API配置保存] 开始测试 API 连接...")
        from utils.helpers import test_api_connection
        connected, conn_msg = test_api_connection(api_key, api_base, model_name)
        logger.info(f"[API配置保存] 连接测试结果: 成功={connected}, 消息={conn_msg}")

        if not connected:
            logger.error(f"[API配置保存] 连接测试失败: {conn_msg}")
            return {"success": False, "message": conn_msg}

        logger.info("[API配置保存] 连接测试成功，保存配置到文件...")
        config.api_key = api_key
        config.api_base = api_base
        config.model_name = model_name
        config.temperature = config_data.get("temperature", 0.7)
        config.max_tokens = config_data.get("max_tokens", 32000)
        config.max_context_tokens = config_data.get("max_context_tokens", 128000)
        success, message = config.save_to_file()
        logger.info(f"[API配置保存] 配置保存结果: 成功={success}, 消息={message}")

        if success:
            logger.info("[API配置保存] 配置保存成功！")
            return {"success": True, "message": f"{conn_msg}\n\n{message}"}
        else:
            logger.error(f"[API配置保存] 配置保存失败: {message}")
            return {"success": False, "message": message}

    def get_ui_config(self):
        return {
            "web_ai_assist": config.web_ai_assist,
            "web_include_images": config.web_include_images,
            "conv_ai_assist": config.conv_ai_assist,
            "integration_strategy": config.integration_strategy,
            "auto_topic": config.auto_topic,
            "topic_list": config.topic_list
        }

    def save_ui_config(self, ui_config):
        config.web_ai_assist = ui_config.get("web_ai_assist", False)
        config.web_include_images = ui_config.get("web_include_images", False)
        config.conv_ai_assist = ui_config.get("conv_ai_assist", False)
        config.integration_strategy = ui_config.get("integration_strategy", "ml")
        config.auto_topic = ui_config.get("auto_topic", True)
        config.topic_list = ui_config.get("topic_list", "")
        success, message = config.save_to_file()
        return success, message

    def get_theme_preference(self):
        return getattr(config, 'theme_preference', 'system')

    def save_theme_preference(self, theme):
        config.theme_preference = theme
        config.save_to_file()

    def get_workspace_tree(self):
        workspace_path = config.workspace_path
        if not workspace_path or not Path(workspace_path).exists():
            return []

        def build_tree(path, relative_base=None):
            if relative_base is None:
                relative_base = path

            items = []
            try:
                entries = list(Path(path).iterdir())
                dirs = []
                files = []
                for item in entries:
                    if item.name.startswith('.'):
                        continue
                    rel_path = str(item.relative_to(relative_base))
                    if item.is_dir():
                        children = build_tree(item, relative_base)
                        dirs.append({
                            "name": item.name,
                            "path": rel_path,
                            "type": "folder",
                            "children": children
                        })
                    else:
                        if item.suffix.lower() in ['.md', '.txt', '.markdown', '.pdf', '.doc', '.docx']:
                            stat = item.stat()
                            files.append({
                                "name": item.name,
                                "path": rel_path,
                                "type": "file",
                                "size": stat.st_size,
                                "modified": stat.st_mtime
                            })
                dirs.sort(key=lambda x: x['name'].lower())
                files.sort(key=lambda x: x['name'].lower())
                items.extend(dirs)
                items.extend(files)
            except PermissionError:
                pass

            return items

        return build_tree(workspace_path)

    def on_file_selected(self, path):
        logger.info(f"文件选中: {path}")

    def get_file_preview(self, path):
        try:
            workspace_path = config.workspace_path
            previewer = FilePreviewer(workspace_path)

            if not previewer.can_preview(path):
                return {
                    'success': False,
                    'error': '不支持预览此文件类型'
                }

            result = previewer.get_preview_data(path)
            return result

        except Exception as e:
            logger.error(f"get_file_preview: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

    def can_preview_file(self, path):
        previewer = FilePreviewer()
        return previewer.can_preview(path)

    def save_file_content(self, path, content):
        try:
            workspace_path = config.workspace_path

            if workspace_path and not Path(path).is_absolute():
                full_path = Path(workspace_path) / path
            else:
                full_path = Path(path)

            full_path.parent.mkdir(parents=True, exist_ok=True)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"文件已保存: {full_path}")

            return {
                'success': True,
                'message': f'已保存: {full_path.name}'
            }

        except Exception as e:
            logger.error(f"保存文件失败 {path}: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }


def try_restore_workspace_config():
    try:
        workspace_info = workspace_manager.get_workspace_info()

        is_saved = workspace_info.get("is_saved", False)
        is_valid = workspace_info.get("is_valid", False)
        saved_path = workspace_info.get("saved_path")
        workspace_path = workspace_info.get("workspace_path")

        if not is_saved:
            print(f"[INFO] 没有保存的工作区状态")
            return None, "没有保存的工作区"

        if not is_valid:
            print(f"[INFO] 已保存的工作区路径不存在: {saved_path}")
            return None, f"工作区路径已不存在: {saved_path}"

        if not workspace_path:
            print(f"[WARNING] 工作区信息不一致: is_valid=True 但 workspace_path=None")
            return None, "工作区状态不一致"

        workspace = Path(workspace_path)

        config.workspace_path = workspace_path

        success, message = config.setup_workspace_folders()
        if not success:
            print(f"[WARNING] 设置工作区文件夹失败: {message}")

        workspace_name = workspace.name

        print(f"[INFO] 已自动恢复工作区配置: {workspace_path}")
        return workspace_name, f"已恢复工作区: {workspace_name}"

    except Exception as e:
        print(f"[ERROR] 恢复工作区配置时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return None, f"恢复工作区失败: {str(e)}"


def _download_codemirror_bundle(webui_dir):
    import urllib.request
    bundle_path = Path(webui_dir) / 'codemirror-bundle.mjs'
    if bundle_path.exists():
        print(f"[INFO] CodeMirror bundle already exists: {bundle_path}")
        return True
    print("[INFO] Downloading CodeMirror bundle...")
    try:
        entry_url = 'https://esm.sh/codemirror@6.0.1?bundle&deps=@codemirror/lang-markdown@6.2.5,@codemirror/theme-one-dark@6.1.2,@codemirror/theme-one-light@6.1.2,@codemirror/commands@6.6.0,@codemirror/autocomplete@6.16.0,@codemirror/lint@6.8.0'
        req = urllib.request.Request(entry_url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req)
        entry_content = resp.read().decode('utf-8')

        match = re.search(r'export \* from "(/[^"]+\.bundle\.mjs)"', entry_content)
        if not match:
            print("[WARNING] Could not find bundle URL in esm.sh entry")
            return False

        bundle_url = 'https://esm.sh' + match.group(1)
        print(f"[INFO] Downloading bundle from: {bundle_url}")
        urllib.request.urlretrieve(bundle_url, str(bundle_path))
        print(f"[INFO] CodeMirror bundle downloaded: {bundle_path} ({bundle_path.stat().st_size} bytes)")
        return True
    except Exception as e:
        print(f"[WARNING] Failed to download CodeMirror bundle: {e}")
        import traceback
        traceback.print_exc()
        return False


def _start_http_server_with_api(directory, api):
    import threading
    import socket
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    class APIRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self._api = api
            super().__init__(*args, directory=directory, **kwargs)

        def end_headers(self):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            super().end_headers()

        def do_OPTIONS(self):
            self.send_response(200)
            self.end_headers()

        def do_GET(self):
            parsed_path = urlparse(self.path)
            path = parsed_path.path

            if path.startswith('/api/'):
                self._handle_api_get(path, parsed_path.query)
                return

            super().do_GET()

        def do_POST(self):
            parsed_path = urlparse(self.path)
            path = parsed_path.path

            if path.startswith('/api/'):
                self._handle_api_post(path)
                return

            self.send_response(404)
            self.end_headers()

        def _handle_api_get(self, path, query):
            try:
                method_name = path[5:]
                params = parse_qs(query)
                args_json = params.get('args', ['[]'])[0]
                args = json.loads(args_json)

                result = self._call_api_method(method_name, args)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))

            except Exception as e:
                print(f"[ERROR] API GET 调用失败: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))

        def _handle_api_post(self, path):
            try:
                method_name = path[5:]

                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode('utf-8')
                args = json.loads(body) if body else []

                result = self._call_api_method(method_name, args)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))

            except Exception as e:
                print(f"[ERROR] API POST 调用失败: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode('utf-8'))

        def _call_api_method(self, method_name, args):
            if method_name.startswith('_'):
                raise ValueError(f"私有方法不可调用: {method_name}")

            if not hasattr(self._api, method_name):
                raise ValueError(f"API 方法不存在: {method_name}")

            method = getattr(self._api, method_name)

            if isinstance(args, list):
                return method(*args)
            elif isinstance(args, dict):
                return method(**args)
            else:
                return method(args)

        def log_message(self, format, *args):
            pass

    def find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    port = find_free_port()

    server = HTTPServer(('localhost', port), APIRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[INFO] HTTP server with API started on http://localhost:{port}")
    return port


def main():
    """开发模式：启动 HTTP API 服务器（用于前端调试）"""
    html_path = Path(__file__).parent / "index.html"
    _download_codemirror_bundle(str(html_path.parent))

    api = Api()

    http_port = _start_http_server_with_api(str(html_path.parent), api)

    workspace_name, message = try_restore_workspace_config()
    if workspace_name:
        print(f"[INFO] 已恢复工作区: {workspace_name}")

    print(f"[INFO] 开发服务器已启动: http://localhost:{http_port}/index.html?port={http_port}")
    print("[INFO] 按 Ctrl+C 停止服务器")

    try:
        import signal
        signal.pause()
    except KeyboardInterrupt:
        print("\n[INFO] 服务器已停止")


if __name__ == "__main__":
    main()
