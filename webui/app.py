"""
NoteAI WebView 应用 - 使用 PySide6 QtWebEngine

通信机制：
- JS -> Python: 使用 HTTP API (fetch POST /api/method)
- Python -> JS: 使用 QWebEnginePage.runJavaScript() + JSBridge 信号槽
"""

import sys
import json
import shutil
import re
from pathlib import Path
from urllib.parse import unquote, parse_qs, urlparse

from PySide6.QtCore import Qt, QUrl, Slot, QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QFileDialog
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtGui import QShortcut, QKeySequence

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


class JSBridge(QObject):
    """线程安全的 JavaScript 桥接
    
    确保所有 JS 执行都在主线程中进行。
    注意：必须在主线程中创建此对象（在 MainWindow._setup_ui() 中创建）。
    """
    execute_js = Signal(str)  # 只传递 js_code 字符串

    def __init__(self, web_view):
        super().__init__()
        self._web_view = web_view
        self.execute_js.connect(self._do_execute_js)

    @Slot(str)
    def _do_execute_js(self, js_code):
        """在主线程中执行 JavaScript"""
        if self._web_view and self._web_view.page():
            self._web_view.page().runJavaScript(js_code)

    def run_js(self, js_code):
        """从任何线程调用，自动切换到主线程执行"""
        self.execute_js.emit(str(js_code))


class Api:
    """暴露给 JavaScript 的 API"""

    def __init__(self):
        self.window = None
        self._close_requested = False

    def set_window(self, window):
        self.window = window

    def move_window(self, dx, dy):
        if self.window:
            w = self.window
            QTimer.singleShot(0, lambda _w=w, _dx=dx, _dy=dy: _w.move(int(_dx), int(_dy)))

    def start_system_move(self):
        if self.window:
            w = self.window
            QTimer.singleShot(0, lambda: w.start_system_move())

    def minimize_window(self):
        if self.window:
            w = self.window
            QTimer.singleShot(0, lambda: w.minimize())

    def maximize_window(self):
        if self.window:
            w = self.window
            QTimer.singleShot(0, lambda: w.maximize())

    def close_window(self):
        self._close_requested = True
        if self.window:
            w = self.window
            QTimer.singleShot(0, lambda: w.close())

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

    def update_window_title(self):
        if self.window and config.is_workspace_set():
            workspace_name = Path(config.workspace_path).name
            self.window.set_title(f"NoteAI - {workspace_name}")

    def open_workspace(self):
        try:
            result = self.window.create_file_dialog(
                'folder',
                directory=str(Path.home()),
                allow_multiple=False
            )
            print(f"[DEBUG] open_workspace result: {result}")
            if result:
                if isinstance(result, (list, tuple)) and len(result) > 0:
                    workspace_path = str(Path(result[0]))
                else:
                    workspace_path = str(Path(result))

                config.workspace_path = workspace_path
                setup_success, setup_message = config.setup_workspace_folders()

                config.save_to_file()

                ws_save_success, ws_save_message = workspace_manager.save_workspace(workspace_path)
                if not ws_save_success:
                    print(f"[WARNING] 保存工作区到系统目录失败: {ws_save_message}")
                else:
                    print(f"[INFO] {ws_save_message}")

                workspace_name = Path(workspace_path).name
                self.window.set_title(f"NoteAI - {workspace_name}")

                final_message = setup_message
                if not ws_save_success:
                    final_message = f"{setup_message}\n（警告：工作区状态保存失败）"

                return {
                    "success": setup_success,
                    "message": final_message,
                    "workspace_path": workspace_path,
                    "notes_folder": config.get_notes_folder(),
                    "organized_folder": config.get_organized_folder()
                }
            return {"success": False, "message": "未选择文件夹", "workspace_path": "", "notes_folder": "", "organized_folder": ""}
        except Exception as e:
            print(f"[ERROR] open_workspace: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e), "workspace_path": "", "notes_folder": "", "organized_folder": ""}

    def get_api_config(self):
        masked_key = ""
        if config.api_key:
            key = config.api_key.strip()
            if len(key) > 8:
                masked_key = key[:4] + "****" + key[-4:]
            else:
                masked_key = "****"
        return {
            "api_key": masked_key,
            "api_key_configured": bool(config.api_key and config.api_key.strip()),
            "api_base": config.api_base,
            "model_name": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "max_context_tokens": config.max_context_tokens
        }

    def browse_folder(self):
        try:
            result = self.window.create_file_dialog(
                'folder',
                directory=str(Path.home()),
                allow_multiple=False
            )
            print(f"[DEBUG] browse_folder result: {result}")
            if result:
                if isinstance(result, (list, tuple)) and len(result) > 0:
                    return str(Path(result[0]))
                return str(Path(result))
            return None
        except Exception as e:
            print(f"[ERROR] browse_folder: {e}")
            import traceback
            traceback.print_exc()
            return None

    def add_files(self):
        try:
            result = self.window.create_file_dialog(
                'open_files',
                directory=str(Path.home()),
                allow_multiple=True,
                file_types=[
                    '支持的文件 (*.pdf;*.docx;*.pptx;*.txt)',
                    '所有文件 (*.*)'
                ]
            )
            print(f"[DEBUG] add_files result: {result}")
            if result:
                if isinstance(result, (list, tuple)):
                    return [str(Path(p)) for p in result]
                return [str(Path(result))]
            return []
        except Exception as e:
            print(f"[ERROR] add_files: {e}")
            import traceback
            traceback.print_exc()
            return []

    def update_status(self, text):
        self.window.evaluate_js(f'updateStatus({repr(text)})')

    def update_progress(self, element_id, progress, message):
        self.window.evaluate_js(f'updateProgress({repr(element_id)}, {progress}, {repr(message)})')

    def show_message(self, title, message, msg_type="info"):
        self.window.evaluate_js(f'updateStatus({repr(str(message))})')

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
            self.show_message("警告", "请先设置工作文件夹\n\n点击顶部「打开工作区」按钮选择工作文件夹", "warning")
            return

        if not urls:
            self.show_message("警告", "请输入至少一个URL", "warning")
            return

        if ai_assist and not config.validate_api_config():
            self.show_message("警告", "AI辅助模式需要配置有效的API Key\n\n请在设置中配置API，或关闭AI辅助使用基础模式。", "warning")
            return

        save_path = config.get_notes_folder()
        if not save_path:
            self.show_message("错误", "无法获取Notes文件夹路径", "error")
            return

        def task():
            try:
                def progress_callback(current, total, message):
                    self.window.evaluate_js(
                        f'updateProgress("web-progress", {current/total if total > 0 else 0}, {repr(message)})'
                    )
                    self.update_status(message)

                downloader = WebDownloader(progress_callback, ai_assist=ai_assist, include_images=include_images)
                results = downloader.download_batch(urls, save_path)

                success_count = sum(1 for r in results if r["success"])
                mode_text = "AI辅助" if ai_assist else "基础"
                self.update_status(f"下载完成（{mode_text}模式）：{success_count}/{len(results)}")

                new_md_files = [r["file_path"] for r in results if r.get("success") and r.get("file_path", "").endswith(".md")]
                if new_md_files:
                    self._tag_new_files(new_md_files)
            except APIConfigError as e:
                error_msg = f"任务中断：{str(e)}\n\n请先配置有效的 API Key 后再试，或关闭AI辅助使用基础模式。"
                self.show_message("错误", error_msg, "error")
                self.update_status("任务中断：API配置错误")
            except NetworkError as e:
                error_msg = f"{str(e)}"
                self.show_message("网络错误", error_msg, "error")
                self.update_status("任务中断：网络连接错误")
            except Exception as e:
                self.show_message("错误", str(e), "error")

        threading.Thread(target=task, daemon=True).start()

    def start_file_conversion(self, ai_assist=False):
        import threading
        if not config.is_workspace_set():
            self.show_message("警告", "请先设置工作文件夹\n\n点击顶部「打开工作区」按钮选择工作文件夹", "warning")
            return

        if ai_assist and not config.validate_api_config():
            self.show_message("警告", "AI辅助模式需要配置有效的API Key\n\n请在设置中配置API，或关闭AI辅助使用基础模式。", "warning")
            return

        save_path = config.get_notes_folder()
        raw_path = config.get_raw_folder()
        workspace_path = config.workspace_path
        if not save_path or not workspace_path:
            self.show_message("错误", "无法获取工作文件夹路径", "error")
            return

        def task():
            try:
                def progress_callback(current, total, message):
                    self.window.evaluate_js(
                        f'updateProgress("conv-progress", {current/total if total > 0 else 0}, {repr(message)})'
                    )
                    self.update_status(message)

                converter = FileConverterManager(progress_callback)

                self.window.evaluate_js(f'updateProgress("conv-progress", 0, {repr("正在扫描工作文件夹...")})')
                results = converter.convert_folder(workspace_path, save_path, raw_path, recursive=True, ai_assist=ai_assist)

                success_count = sum(1 for r in results if r["success"])
                mode_text = "AI辅助" if ai_assist else "基础"
                self.update_status(f"转换完成（{mode_text}模式）：{success_count}/{len(results)}")

                new_md_files = [r["file_path"] for r in results if r.get("success") and r.get("file_path", "").endswith(".md")]
                if new_md_files:
                    self._tag_new_files(new_md_files)
            except APIConfigError as e:
                error_msg = f"任务中断：{str(e)}\n\n请先配置有效的 API Key 后再试。"
                self.show_message("错误", error_msg, "error")
                self.update_status("任务中断：API配置错误")
            except NetworkError as e:
                error_msg = f"{str(e)}"
                self.show_message("网络错误", error_msg, "error")
                self.update_status("任务中断：网络连接错误")
            except Exception as e:
                self.show_message("错误", str(e), "error")

        threading.Thread(target=task, daemon=True).start()

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

        def progress_callback(current, total, message):
            try:
                progress = current / total if total > 0 else 0
                self.window.evaluate_js(
                    f'updateProgress("integration-progress", {progress}, {repr(message)})'
                )
                self.update_status(message)
            except Exception as e:
                print(f"[WARNING] 更新进度失败: {e}")

        try:
            extractor = TopicExtractor(progress_callback=progress_callback)
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
            self.show_message("警告", "请先设置工作文件夹\n\n点击顶部「打开工作区」按钮选择工作文件夹", "warning")
            return

        if not topics:
            self.show_message("警告", "请先提取主题\n\n点击「提取主题」按钮获取主题列表后再整合", "warning")
            return

        source_path = config.get_notes_folder()
        output_path = config.get_organized_folder()
        used_path = config.get_used_folder()

        if not source_path or not output_path:
            self.show_message("错误", "无法获取工作文件夹路径", "error")
            return

        def task():
            doc_paths = []
            try:
                def progress_callback(current, total, message, max_total=1.0):
                    effective_progress = (current / total) * max_total if total > 0 else 0
                    self.window.evaluate_js(
                        f'updateProgress("integration-progress", {effective_progress}, {repr(message)})'
                    )
                    self.update_status(message)

                Path(output_path).mkdir(parents=True, exist_ok=True)
                Path(used_path).mkdir(parents=True, exist_ok=True)

                integrator = NoteIntegration(progress_callback)
                documents = integrator.load_documents_from_folder(source_path)

                if not documents:
                    self.show_message("警告", "未找到Markdown文件", "warning")
                    return

                doc_paths = [d['path'] for d in documents]

                result = integrator.integrate(documents, output_path, user_topics=topics)

                self.show_message("完成", f"整合完成！\n处理了 {result['document_count']} 篇文档\n生成了 {result['topic_count']} 个主题\n保存至: {output_path}")

            except APIConfigError as e:
                error_msg = f"任务中断：{str(e)}\n\n请先配置有效的 API Key 后再试。"
                self.show_message("错误", error_msg, "error")
                self.update_status("任务中断：API配置错误")
            except NetworkError as e:
                error_msg = f"{str(e)}"
                self.show_message("网络错误", error_msg, "error")
                self.update_status("任务中断：网络连接错误")
            except Exception as e:
                self.show_message("错误", str(e), "error")
            finally:
                if doc_paths:
                    self._move_docs_to_used(doc_paths, used_path)

        threading.Thread(target=task, daemon=True).start()

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

        if "****" in api_key:
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
        config.temperature = config_data.get("temperature", 0.7)
        config.max_tokens = config_data.get("max_tokens", 32000)
        config.max_context_tokens = config_data.get("max_context_tokens", 128000)
        success, message = config.save_to_file()
        if success:
            return {"success": True, "message": f"{conn_msg}\n\n{message}"}
        else:
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
        return {"success": success, "message": message}

    def refresh_log(self):
        logs = logger.get_logs(200)
        log_text = "".join(logs)
        self.window.evaluate_js(f'document.getElementById("log-text").value = {repr(log_text)}')

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
        print(f"[DEBUG] 文件选中: {path}")
        self.update_status(f"选中文件: {path}")

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
            print(f"[ERROR] get_file_preview: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

    def can_preview_file(self, path):
        previewer = FilePreviewer()
        return previewer.can_preview(path)

    def show_about(self):
        self.show_message(
            "关于 NoteAI",
            "NoteAI - AI驱动的Markdown笔记知识库管理\n\n"
            "版本: 1.0.0\n"
            "功能:\n"
            "- 网络文章批量下载与转换\n"
            "- 多格式文件转换\n"
            "- 智能笔记主题整合\n\n"
            "使用PySide6 + HTML/CSS/JS开发"
        )

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


class MainWindow(QMainWindow):
    """主窗口 - 无边框设计"""

    def __init__(self):
        super().__init__()
        self._is_maximized = False
        self._normal_geometry = None
        self._web_view = None
        self._api = None
        self._js_bridge = None  # JSBridge 实例（在主线程创建）

        self._setup_ui()

    def _setup_ui(self):
        """设置 UI"""
        self.setWindowTitle("NoteAI")
        self.setMinimumSize(1000, 700)
        self.resize(1400, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._web_view = QWebEngineView()
        
        self._js_bridge = JSBridge(self._web_view)
        
        layout.addWidget(self._web_view)

        self._setup_shortcuts()

    def showEvent(self, event):
        """窗口首次显示时配置 macOS 透明标题栏"""
        super().showEvent(event)
        if not hasattr(self, '_macos_titlebar_configured'):
            self._macos_titlebar_configured = True
            self._setup_macos_titlebar()

    def _setup_macos_titlebar(self):
        """配置 macOS 透明标题栏（保留原生红绿灯按钮，类似 Obsidian）"""
        import sys
        if sys.platform != 'darwin':
            return
        try:
            from AppKit import NSWindow, NSWindowTitleVisibility
            handle = self.windowHandle()
            if not handle:
                return
            ns_view = handle.nsView()
            if not ns_view:
                return
            ns_window = ns_view.window()
            ns_window.setTitlebarAppearsTransparent_(True)
            ns_window.setTitleVisibility_(NSWindowTitleHidden)
            style_mask = ns_window.styleMask()
            ns_window.setStyleMask_(style_mask | NSWindow.StyleMaskFullSizeContentView)
            logger.info("macOS 透明标题栏已配置")
        except Exception as e:
            logger.warning(f"配置 macOS 透明标题栏失败: {e}")

    def set_api(self, api):
        """设置 API 对象"""
        self._api = api

    def load_url(self, url):
        """加载 URL 或 HTML 文件"""
        if isinstance(url, Path):
            url = QUrl.fromLocalFile(str(url))
        elif isinstance(url, str):
            if url.startswith("http://") or url.startswith("https://"):
                url = QUrl(url)
            else:
                url = QUrl.fromLocalFile(url)
        self._web_view.setUrl(url)

    def load_html(self, html_content, base_url=None):
        """直接加载 HTML 内容"""
        if base_url:
            self._web_view.setHtml(html_content, QUrl(base_url))
        else:
            self._web_view.setHtml(html_content)

    def evaluate_js(self, js_code):
        """在 WebView 中执行 JavaScript（线程安全）
        
        可以从任何线程调用，自动切换到主线程执行。
        """
        if self._js_bridge:
            self._js_bridge.run_js(js_code)

    def set_title(self, title):
        """设置窗口标题"""
        self.setWindowTitle(title)

    def minimize(self):
        """最小化窗口"""
        self.showMinimized()

    def maximize(self):
        """最大化/还原窗口"""
        self._toggle_maximize()

    def destroy(self):
        """关闭窗口"""
        self.close()

    @property
    def x(self):
        return self.geometry().x()

    @property
    def y(self):
        return self.geometry().y()

    def move(self, x, y):
        """移动窗口"""
        geo = self.geometry()
        geo.moveTo(int(x), int(y))
        self.setGeometry(geo)

    def start_system_move(self):
        """使用系统原生拖拽移动窗口"""
        handle = self.windowHandle()
        if handle:
            handle.startSystemMove()

    def _toggle_maximize(self):
        """切换最大化/还原"""
        if self._is_maximized:
            self.setGeometry(self._normal_geometry)
            self._is_maximized = False
        else:
            self._normal_geometry = self.geometry()
            self.showMaximized()
            self._is_maximized = True

    def closeEvent(self, event):
        """重写关闭事件，确保应用退出"""
        if self._api and hasattr(self._api, '_http_server'):
            try:
                self._api._http_server.shutdown()
            except Exception:
                pass
        event.accept()
        QApplication.instance().quit()

    def _setup_shortcuts(self):
        """设置快捷键"""
        close_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        close_shortcut.activated.connect(self.close)

        fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        fullscreen_shortcut.activated.connect(self._toggle_maximize)

    def create_file_dialog(self, dialog_type, directory=None, allow_multiple=False, file_types=None):
        """
        文件对话框

        dialog_type:
        - 'folder': 文件夹选择
        - 'open_file': 单个文件
        - 'open_files': 多个文件
        """
        if directory is None:
            directory = str(Path.home())

        if dialog_type == 'folder':
            folder = QFileDialog.getExistingDirectory(self, "选择文件夹", directory)
            if folder:
                return [folder] if allow_multiple else folder
            return None

        elif dialog_type == 'open_file':
            file_filter = self._build_file_filter(file_types)
            file_path, _ = QFileDialog.getOpenFileName(self, "选择文件", directory, file_filter)
            if file_path:
                return [file_path] if allow_multiple else file_path
            return None

        elif dialog_type == 'open_files':
            file_filter = self._build_file_filter(file_types)
            files, _ = QFileDialog.getOpenFileNames(self, "选择文件", directory, file_filter)
            return files if files else None

        return None

    def _build_file_filter(self, file_types):
        """构建文件过滤器字符串"""
        if not file_types:
            return "所有文件 (*.*)"

        if isinstance(file_types, (list, tuple)):
            filters = []
            for ft in file_types:
                if isinstance(ft, str) and '(' in ft:
                    filters.append(ft)
                else:
                    filters.append(str(ft))
            return ";;".join(filters)

        return "所有文件 (*.*)"


def try_restore_workspace_config():
    """尝试从系统目录恢复工作区配置"""
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


def _build_codemirror_bundle(webui_dir):
    """使用 esbuild 构建 CodeMirror bundle（用于 MD 编辑器）"""
    import subprocess
    bundle_path = Path(webui_dir) / 'codemirror-bundle.mjs'
    if bundle_path.exists():
        print(f"[INFO] CodeMirror bundle already exists: {bundle_path}")
        return True

    print("[INFO] Building CodeMirror bundle with esbuild...")
    build_dir = Path(webui_dir) / '_cm_build'
    try:
        build_dir.mkdir(parents=True, exist_ok=True)

        entry_content = '''export { EditorState, EditorSelection } from "@codemirror/state";
export { EditorView, keymap } from "@codemirror/view";
export { basicSetup } from "codemirror";
export { markdown } from "@codemirror/lang-markdown";
export { oneDark } from "@codemirror/theme-one-dark";
export { indentWithTab, defaultKeymap, historyKeymap } from "@codemirror/commands";
export { closeBracketsKeymap, completionKeymap } from "@codemirror/autocomplete";
export { lintKeymap } from "@codemirror/lint";
import { EditorView } from "@codemirror/view";
const oneLightTheme = EditorView.theme({"&":{backgroundColor:"#ffffff",color:"#333333"},".cm-content":{caretColor:"#333333"},".cm-cursor, .cm-dropCursor":{borderLeftColor:"#333333"},"&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":{backgroundColor:"#d7d4f0"},".cm-gutters":{backgroundColor:"#f7f7f7",color:"#999999",border:"none"},".cm-activeLineGutter":{backgroundColor:"#e8e8e8"},".cm-activeLine":{backgroundColor:"#f0f0f0"}},{dark:false});
export const oneLight = [oneLightTheme];
'''
        (build_dir / 'entry.mjs').write_text(entry_content, encoding='utf-8')

        pkg_json = '''{"type":"module","dependencies":{"codemirror":"^6.0.1","@codemirror/state":"^6.5.2","@codemirror/view":"^6.36.0","@codemirror/lang-markdown":"^6.3.1","@codemirror/theme-one-dark":"^6.1.2","@codemirror/commands":"^6.7.1","@codemirror/autocomplete":"^6.18.4","@codemirror/lint":"^6.8.2"},"devDependencies":{"esbuild":"^0.25.0"}}'''
        (build_dir / 'package.json').write_text(pkg_json, encoding='utf-8')

        print("[INFO] Installing npm dependencies...")
        subprocess.run(['npm', 'install'], cwd=str(build_dir), capture_output=True, check=True)

        print("[INFO] Bundling with esbuild...")
        subprocess.run([
            'npx', 'esbuild', 'entry.mjs',
            '--bundle', '--format=esm',
            '--outfile=' + str(bundle_path),
            '--minify'
        ], cwd=str(build_dir), capture_output=True, check=True)

        print(f"[INFO] CodeMirror bundle built: {bundle_path} ({bundle_path.stat().st_size} bytes)")
        return True
    except Exception as e:
        print(f"[WARNING] Failed to build CodeMirror bundle: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        import shutil
        if build_dir.exists():
            shutil.rmtree(str(build_dir), ignore_errors=True)


def _start_http_server_with_api(directory, api):
    """启动本地 HTTP 服务器，支持静态文件和 API 调用"""
    import threading
    import socket
    import secrets
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    api_token = secrets.token_hex(32)

    class APIRequestHandler(SimpleHTTPRequestHandler):
        extensions_map = {
            **SimpleHTTPRequestHandler.extensions_map,
            '.mjs': 'application/javascript',
            '.js': 'application/javascript',
            '.css': 'text/css',
            '.html': 'text/html',
            '.json': 'application/json',
            '.wasm': 'application/wasm',
            '.map': 'application/json',
        }

        def __init__(self, *args, **kwargs):
            self._api = api
            self._token = api_token
            super().__init__(*args, directory=directory, **kwargs)

        def end_headers(self):
            self.send_header('Access-Control-Allow-Origin', f'http://localhost:{self.server.server_address[1]}')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Token')
            super().end_headers()

        def _verify_token(self):
            token = self.headers.get('X-API-Token', '')
            if not token:
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                token = params.get('token', [''])[0]
            if not secrets.compare_digest(token, self._token):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": "认证失败"}).encode('utf-8'))
                return False
            return True

        def do_OPTIONS(self):
            self.send_response(200)
            self.end_headers()

        def do_GET(self):
            parsed_path = urlparse(self.path)
            path = parsed_path.path

            if path.startswith('/api/'):
                if not self._verify_token():
                    return
                self._handle_api_get(path, parsed_path.query)
                return

            if path.startswith('/files/'):
                if not self._verify_token():
                    return
                self._serve_workspace_file(path)
                return

            super().do_GET()

        def _serve_workspace_file(self, path):
            """提供工作区文件的只读访问（用于 PDF.js 等前端渲染）"""
            import os
            import urllib.parse
            from config.settings import config

            if not config.workspace_path:
                self.send_response(404)
                self.end_headers()
                return

            relative_path = path[len('/files/'):]
            relative_path = urllib.parse.unquote(relative_path)

            file_path = os.path.normpath(os.path.join(config.workspace_path, relative_path))

            if not file_path.startswith(os.path.normpath(config.workspace_path)):
                self.send_response(403)
                self.end_headers()
                return

            if not os.path.isfile(file_path):
                self.send_response(404)
                self.end_headers()
                return

            try:
                file_size = os.path.getsize(file_path)
                ext = os.path.splitext(file_path)[1].lower()
                mime_types = {
                    '.pdf': 'application/pdf',
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.svg': 'image/svg+xml',
                    '.webp': 'image/webp',
                }
                mime_type = mime_types.get(ext, 'application/octet-stream')

                self.send_response(200)
                self.send_header('Content-Type', mime_type)
                self.send_header('Content-Length', str(file_size))
                encoded_name = urllib.parse.quote(os.path.basename(file_path))
                self.send_header('Content-Disposition', f"inline; filename*=UTF-8''{encoded_name}")
                self.end_headers()

                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except Exception as e:
                print(f"[ERROR] Serving file {path}: {e}")
                self.send_response(500)
                self.end_headers()

        def do_POST(self):
            parsed_path = urlparse(self.path)
            path = parsed_path.path

            if path.startswith('/api/'):
                if not self._verify_token():
                    return
                self._handle_api_post(path)
                return

            self.send_response(404)
            self.end_headers()

        def _handle_api_get(self, path, query):
            """处理 GET API 请求（用于简单调用）"""
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
            """处理 POST API 请求"""
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

        _ALLOWED_API_METHODS = {
            'get_workspace_status', 'check_workspace_path_valid', 'clear_saved_workspace',
            'update_window_title', 'open_workspace', 'get_api_config', 'browse_folder',
            'add_files', 'update_status', 'update_progress', 'show_message',
            'start_web_download', 'start_file_conversion', 'extract_topics',
            'start_note_integration', 'save_api_config', 'get_ui_config', 'save_ui_config',
            'refresh_log', 'get_theme_preference', 'save_theme_preference',
            'get_workspace_tree', 'on_file_selected', 'get_file_preview',
            'can_preview_file', 'show_about', 'save_file_content',
            'move_window', 'start_system_move', 'minimize_window', 'maximize_window', 'close_window',
        }

        def _call_api_method(self, method_name, args):
            """调用 API 方法"""
            if method_name not in self._ALLOWED_API_METHODS:
                raise ValueError(f"API 方法不存在或不可调用: {method_name}")

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

    api._http_server = server
    return port, api_token


def main():
    """启动 PySide6 版本应用"""
    import os
    import signal
    os.environ['QT_MAC_WANTS_LAYER'] = '1'

    app = QApplication(sys.argv)
    app.setApplicationName("NoteAI")
    app.setOrganizationName("NoteAI")

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    html_path = Path(__file__).parent / "index.html"
    _build_codemirror_bundle(str(html_path.parent))

    window = MainWindow()
    api = Api()
    api.set_window(window)

    http_port, http_token = _start_http_server_with_api(str(html_path.parent), api)

    workspace_name, message = try_restore_workspace_config()
    if workspace_name:
        try:
            window.set_title(f"NoteAI - {workspace_name}")
            print(f"[INFO] 已设置窗口标题: NoteAI - {workspace_name}")
        except Exception as e:
            print(f"[WARNING] 设置窗口标题失败: {e}")

    index_url = f"http://localhost:{http_port}/index.html?port={http_port}&token={http_token}"
    window.load_url(index_url)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
