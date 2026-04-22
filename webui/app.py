"""
Webview 应用 - 使用 HTML/CSS/JS 做 UI，Python 做后端
"""

import sys
import re
import shutil
from pathlib import Path
import threading
import webview
from webview import FileDialog

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import config, workspace_manager
from utils.logger import logger
from utils.helpers import APIConfigError, NetworkError, is_network_error, test_api_connection, check_api_config
from modules.web_downloader import WebDownloader
from modules.file_converter import FileConverterManager
from modules.note_integration import NoteIntegration
from modules.file_preview import FilePreviewer
from utils.tag_extractor import tag_markdown_files


class Api:
    """暴露给 JavaScript 的 API"""

    def __init__(self):
        self.window = None

    def set_window(self, window):
        self.window = window

    def move_window(self, dx, dy):
        """根据增量移动窗口"""
        if self.window:
            try:
                x = self.window.x + dx
                y = self.window.y + dy
                self.window.move(x, y)
            except Exception as e:
                print(f"移动窗口失败: {e}")

    def minimize_window(self):
        """最小化窗口"""
        if self.window:
            self.window.minimize()

    def maximize_window(self):
        """最大化/还原窗口"""
        if self.window:
            if self.window.attributes['fullscreen']:
                self.window.set_fullscreen(False)
            else:
                self.window.set_fullscreen(True)

    def close_window(self):
        """关闭窗口并退出应用"""
        import webview
        if self.window:
            self.window.destroy()
        webview.quit()
        sys.exit(0)

    def get_workspace_status(self):
        """获取工作文件夹状态"""
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
        """检查当前工作区路径是否仍然有效
        
        用于检测工作区路径是否被删除、移动等情况
        """
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
        """清除系统目录中保存的工作区状态
        
        当用户不想自动恢复工作区时使用
        """
        success, message = workspace_manager.clear_workspace_state()
        return {
            "success": success,
            "message": message
        }

    def update_window_title(self):
        """更新窗口标题"""
        if self.window and config.is_workspace_set():
            workspace_name = Path(config.workspace_path).name
            self.window.set_title(f"NoteAI - {workspace_name}")

    def open_workspace(self):
        """打开工作区对话框并设置工作文件夹
        
        此方法会：
        1. 让用户选择文件夹
        2. 设置工作区路径
        3. 创建标准子文件夹
        4. 同时保存到项目配置文件和系统应用数据目录（双重保存）
        5. 无论之前是否有保存的工作区，都会覆盖更新系统目录
        """
        try:
            result = self.window.create_file_dialog(
                FileDialog.FOLDER,
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

    def get_default_path(self):
        """获取默认保存路径"""
        return config.default_save_path
    
    def get_api_config(self):
        """获取 API 配置"""
        return {
            "api_key": config.api_key,
            "api_base": config.api_base,
            "model_name": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "max_context_tokens": config.max_context_tokens
        }
    
    def browse_folder(self):
        """打开文件夹选择对话框"""
        try:
            result = self.window.create_file_dialog(
                FileDialog.FOLDER,
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
        """添加文件"""
        try:
            result = self.window.create_file_dialog(
                FileDialog.OPEN_FILES,
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
        """更新状态栏"""
        self.window.evaluate_js(f'updateStatus({repr(text)})')
    
    def update_progress(self, element_id, progress, message):
        """更新进度条"""
        self.window.evaluate_js(f'updateProgress({repr(element_id)}, {progress}, {repr(message)})')
    
    def show_message(self, title, message, msg_type="info"):
        """静默消息：统一显示在状态栏"""
        self.window.evaluate_js(f'updateStatus({repr(str(message))})')
    
    def _tag_new_files(self, file_paths: list):
        """后台为新建的 Markdown 文件打标签"""
        def bg_task():
            try:
                tagged = tag_markdown_files(file_paths)
                logger.info(f"标签提取完成: {len(tagged)} 个文件")
            except Exception as e:
                logger.warning(f"标签提取失败: {e}")
        threading.Thread(target=bg_task, daemon=True).start()

    def start_web_download(self, urls, ai_assist=False, include_images=False):
        """开始网页下载"""
        if not config.is_workspace_set():
            self.show_message("警告", "请先设置工作文件夹\n\n点击顶部「打开工作区」按钮选择工作文件夹", "warning")
            return

        if not urls:
            self.show_message("警告", "请输入至少一个URL", "warning")
            return

        if ai_assist:
            is_valid, error_msg = check_api_config()
            if not is_valid:
                self.update_status("请先设置大模型 API")
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
        """开始文件转换"""
        if not config.is_workspace_set():
            self.show_message("警告", "请先设置工作文件夹\n\n点击顶部「打开工作区」按钮选择工作文件夹", "warning")
            return

        if ai_assist:
            is_valid, error_msg = check_api_config()
            if not is_valid:
                self.update_status("请先设置大模型 API")
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
    
    def extract_topics(self):
        """从 Notes 目录提取主题
        
        扫描 Notes 目录下所有 MD 文件名，调用 LLM 提取主题列表
        """
        if not config.is_workspace_set():
            return {"success": False, "error": "请先设置工作文件夹"}

        notes_path = config.get_notes_folder()
        if not notes_path:
            return {"success": False, "error": "无法获取 Notes 文件夹路径"}

        notes_dir = Path(notes_path)
        if not notes_dir.exists():
            return {"success": False, "error": "Notes 文件夹不存在"}

        md_files = list(notes_dir.rglob("*.md"))
        if not md_files:
            return {"success": False, "error": "Notes 文件夹中没有 Markdown 文件"}

        is_valid, error_msg = check_api_config()
        if not is_valid:
            self.update_status("请先设置大模型 API")
            return {"success": False, "error": f"API 配置无效: {error_msg}"}

        filenames = [f.stem for f in md_files if not f.name.startswith('.')]
        titles_text = '\n'.join([f"{i+1}. {name}" for i, name in enumerate(filenames)])

        try:
            self.window.evaluate_js('updateProgress("integration-progress", 0.3, "正在调用 LLM 分析主题...")')
            self.update_status("正在调用 LLM 分析主题...")

            from langchain_openai import ChatOpenAI
            from langchain_core.prompts import PromptTemplate
            from prompts.note_integration import TOPIC_INTEGRATION_PROMPT

            prompt = PromptTemplate(
                template=TOPIC_INTEGRATION_PROMPT,
                input_variables=["titles"]
            )
            llm = ChatOpenAI(
                api_key=config.api_key,
                base_url=config.api_base,
                model=config.model_name,
                temperature=0.5,
                max_tokens=config.max_tokens,
                streaming=True
            )
            chain = prompt | llm

            full_content = ""
            thinking_started = False
            topic_section_started = False

            for chunk in chain.stream({"titles": titles_text}):
                token = chunk.content
                full_content += token

                if "---主题列表---" in full_content:
                    topic_section_started = True
                    if not thinking_started:
                        thinking_started = True
                    thinking_part = full_content.split("---主题列表---")[0]
                    thinking_clean = thinking_part.replace("思考过程（自由分析）：", "").strip()
                    escaped = thinking_clean.replace('\\', '\\\\').replace('`', '\\`').replace('\n', '\\n').replace('"', '\\"').replace("'", "\\'")
                    self.window.evaluate_js(f'document.getElementById("integration-status").textContent = "{escaped}"')
                else:
                    thinking_clean = full_content.replace("思考过程（自由分析）：", "").strip()
                    escaped = thinking_clean.replace('\\', '\\\\').replace('`', '\\`').replace('\n', '\\n').replace('"', '\\"').replace("'", "\\'")
                    if escaped:
                        self.window.evaluate_js(f'document.getElementById("integration-status").textContent = "{escaped}"')

            self.window.evaluate_js('updateProgress("integration-progress", 0.7, "正在解析主题结果...")')
            self.update_status("正在解析主题结果...")

            content = full_content.strip()
            topic_section = content
            if "---主题列表---" in content:
                topic_section = content.split("---主题列表---")[-1]

            topics = []
            for line in topic_section.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if '|' in line:
                    name = line.split('|')[0].strip()
                    name = re.sub(r'^主题\d+[：:]\s*', '', name).strip()
                    if name:
                        topics.append(name)
                else:
                    name = re.sub(r'^[\d]+[.、)\s]+', '', line).strip()
                    name = re.sub(r'^主题\d+[：:]\s*', '', name).strip()
                    if name:
                        topics.append(name)

            if not topics:
                return {"success": False, "error": "LLM 未返回有效主题"}

            logger.info(f"提取了 {len(topics)} 个主题: {topics}")
            return {"success": True, "topics": topics}

        except Exception as e:
            logger.error(f"提取主题失败: {e}")
            return {"success": False, "error": f"提取主题失败: {str(e)}"}
    
    def start_note_integration(self, auto_topic, topics):
        """开始笔记整合"""
        if not config.is_workspace_set():
            self.show_message("警告", "请先设置工作文件夹\n\n点击顶部「打开工作区」按钮选择工作文件夹", "warning")
            return

        is_valid, error_msg = check_api_config()
        if not is_valid:
            self.update_status("请先设置大模型 API")
            self.show_message("警告", "请先配置有效的大模型 API\n\n点击顶部「设置」按钮配置 API Key、API Base 和模型名称", "warning")
            return

        source_path = config.get_notes_folder()
        output_path = config.get_organized_folder()
        used_path = config.get_used_folder()

        if not source_path or not output_path:
            self.show_message("错误", "无法获取工作文件夹路径", "error")
            return

        def task():
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

                user_topics = topics if topics else None
                result = integrator.integrate(documents, output_path, user_topics=user_topics)

                used_dir = Path(used_path)
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
                    shutil.move(str(src), str(dst))

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

        threading.Thread(target=task, daemon=True).start()

    def save_api_config(self, config_data):
        """保存 API 配置"""
        api_key = config_data.get("api_key", "")
        api_base = config_data.get("api_base", "https://api.openai.com/v1")
        model_name = config_data.get("model_name", "gpt-4")

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
        """获取用户界面配置"""
        return {
            "web_ai_assist": config.web_ai_assist,
            "web_include_images": config.web_include_images,
            "conv_ai_assist": config.conv_ai_assist,
            "integration_strategy": config.integration_strategy,
            "auto_topic": config.auto_topic,
            "topic_list": config.topic_list
        }

    def save_ui_config(self, ui_config):
        """保存用户界面配置"""
        config.web_ai_assist = ui_config.get("web_ai_assist", False)
        config.web_include_images = ui_config.get("web_include_images", False)
        config.conv_ai_assist = ui_config.get("conv_ai_assist", False)
        config.integration_strategy = ui_config.get("integration_strategy", "ml")
        config.auto_topic = ui_config.get("auto_topic", True)
        config.topic_list = ui_config.get("topic_list", "")
        success, message = config.save_to_file()
        return success, message
    
    def refresh_log(self):
        """刷新日志"""
        logs = logger.get_logs(200)
        log_text = "".join(logs)
        self.window.evaluate_js(f'document.getElementById("log-text").value = {repr(log_text)}')

    def get_theme_preference(self):
        """获取主题偏好"""
        return getattr(config, 'theme_preference', 'system')

    def save_theme_preference(self, theme):
        """保存主题偏好"""
        config.theme_preference = theme
        config.save_to_file()

    def get_workspace_tree(self):
        """获取工作区目录树"""
        workspace_path = config.workspace_path
        if not workspace_path or not Path(workspace_path).exists():
            return []

        def build_tree(path, relative_base=None):
            """递归构建目录树"""
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
        """文件被选中时的回调"""
        print(f"[DEBUG] 文件选中: {path}")
        self.update_status(f"选中文件: {path}")

    def get_file_preview(self, path):
        """获取文件预览内容"""
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
        """检查文件是否可预览"""
        previewer = FilePreviewer()
        return previewer.can_preview(path)

    def show_about(self):
        """显示关于"""
        self.show_message(
            "关于 NoteAI",
            "NoteAI - AI驱动的Markdown笔记知识库管理\n\n"
            "版本: 1.0.0\n"
            "功能:\n"
            "- 网络文章批量下载与转换\n"
            "- 多格式文件转换\n"
            "- 智能笔记主题整合\n\n"
            "使用Webview + HTML/CSS/JS开发"
        )


def try_restore_workspace_config():
    """尝试从系统目录恢复工作区配置（不操作窗口）
    
    此函数在 webview.start() 之前调用，只设置配置，
    不操作窗口（因为窗口尚未初始化）。
    
    Returns:
        (workspace_name: str 或 None, message: str)
        - workspace_name: 如果成功恢复，返回工作区名称
        - message: 描述信息
    """
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


def main():
    """启动应用"""
    api = Api()

    html_path = Path(__file__).parent / "index.html"
    window = webview.create_window(
        "NoteAI",
        url=str(html_path),
        width=1400,
        height=900,
        min_size=(1000, 700),
        js_api=api,
        frameless=True,
        easy_drag=False
    )

    api.set_window(window)
    
    workspace_name, message = try_restore_workspace_config()
    
    def after_window_start():
        """窗口启动后的回调函数
        
        在此函数中可以安全地调用 window.set_title() 等窗口操作
        """
        if workspace_name:
            try:
                window.set_title(f"NoteAI - {workspace_name}")
                print(f"[INFO] 已设置窗口标题: NoteAI - {workspace_name}")
            except Exception as e:
                print(f"[WARNING] 设置窗口标题失败: {e}")
    
    webview.start(func=after_window_start)


if __name__ == "__main__":
    main()
