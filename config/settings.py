import os
import sys
import tempfile
import base64
import threading
from pathlib import Path
from dataclasses import dataclass, field, fields
from typing import Optional, Dict, Any, Tuple
import json
import shutil

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
# 项目配置文件路径
PROJECT_CONFIG_PATH = str(Path(__file__).parent / "config.json")


def get_system_app_data_dir() -> Path:
    """获取系统应用数据目录（跨平台）
    
    - macOS: ~/Library/Application Support/NoteAI
    - Windows: %APPDATA%/NoteAI 或 %LOCALAPPDATA%/NoteAI
    - Linux: ~/.config/NoteAI
    
    Returns:
        应用数据目录的 Path 对象
    """
    app_name = "NoteAI"
    
    if sys.platform == "darwin":
        # macOS
        base_dir = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        # Windows
        base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        # Linux 等
        base_dir = Path.home() / ".config"
    
    return base_dir / app_name


# 系统级工作区配置文件路径
SYSTEM_APP_DATA_DIR = get_system_app_data_dir()
WORKSPACE_STATE_FILE = SYSTEM_APP_DATA_DIR / "workspace_state.json"
API_CONFIG_FILE = SYSTEM_APP_DATA_DIR / "api_config.json"


class WorkspaceStateError(Exception):
    """工作区状态操作异常"""
    pass


class WorkspaceStateManager:
    """工作区状态管理器
    
    负责：
    1. 保存工作区路径到系统指定目录
    2. 从系统指定目录加载工作区路径
    3. 原子写入防止数据损坏
    4. 错误处理和恢复机制
    """
    
    def __init__(self, state_file: Path = None):
        self.state_file = state_file or WORKSPACE_STATE_FILE
        self._ensure_dir_exists()
    
    def _ensure_dir_exists(self):
        """确保目录存在"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            raise WorkspaceStateError(f"无法创建应用数据目录: {e}")
    
    def _atomic_write(self, data: Dict[str, Any]) -> bool:
        """原子写入文件
        
        策略：先写入临时文件，成功后再替换原文件
        防止写入过程中崩溃导致数据损坏
        """
        try:
            temp_dir = self.state_file.parent
            fd, temp_path = tempfile.mkstemp(dir=temp_dir, suffix=".tmp")
            
            try:
                os.close(fd)
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                fsync_fd = os.open(temp_path, os.O_RDONLY)
                try:
                    os.fsync(fsync_fd)
                finally:
                    os.close(fsync_fd)
                
                if self.state_file.exists():
                    old_path = self.state_file.with_suffix(".json.bak")
                    if old_path.exists():
                        old_path.unlink()
                    shutil.copy2(self.state_file, old_path)
                
                shutil.move(temp_path, self.state_file)
                
                return True
            finally:
                if Path(temp_path).exists():
                    try:
                        Path(temp_path).unlink()
                    except Exception:
                        pass
        except PermissionError:
            raise WorkspaceStateError("保存工作区状态失败：没有写入权限")
        except OSError as e:
            raise WorkspaceStateError(f"保存工作区状态失败：{e}")
    
    def save_workspace(self, workspace_path: str, additional_data: Dict[str, Any] = None) -> Tuple[bool, str]:
        """保存工作区状态
        
        Args:
            workspace_path: 工作区路径
            additional_data: 附加数据（可选）
        
        Returns:
            (success, message)
        """
        if not workspace_path:
            return False, "工作区路径为空"
        
        workspace = Path(workspace_path)
        if not workspace.exists():
            return False, f"工作区路径不存在: {workspace_path}"
        
        data = {
            "workspace_path": str(workspace),
            "last_opened_at": self._get_timestamp(),
            "version": "1.0.0"
        }
        
        if additional_data:
            data.update(additional_data)
        
        try:
            success = self._atomic_write(data)
            if success:
                return True, f"工作区已保存: {workspace_path}"
            return False, "保存工作区失败"
        except WorkspaceStateError as e:
            return False, str(e)
    
    def load_workspace(self) -> Tuple[Optional[str], Dict[str, Any]]:
        """加载工作区状态
        
        Returns:
            (workspace_path 或 None, 完整状态数据)
        """
        if not self.state_file.exists():
            return None, {}
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            workspace_path = data.get("workspace_path")
            if workspace_path:
                workspace = Path(workspace_path)
                if not workspace.exists():
                    return None, data
            
            return workspace_path, data
        except json.JSONDecodeError:
            return self._try_restore_from_backup()
        except (PermissionError, OSError) as e:
            print(f"加载工作区状态时出错: {e}")
            return self._try_restore_from_backup()
    
    def _try_restore_from_backup(self) -> Tuple[Optional[str], Dict[str, Any]]:
        """尝试从备份文件恢复"""
        backup_file = self.state_file.with_suffix(".json.bak")
        if not backup_file.exists():
            return None, {}
        
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            workspace_path = data.get("workspace_path")
            if workspace_path:
                workspace = Path(workspace_path)
                if not workspace.exists():
                    return None, data
            
            print("已从备份文件恢复工作区状态")
            return workspace_path, data
        except Exception:
            return None, {}
    
    def clear_workspace_state(self) -> Tuple[bool, str]:
        """清除工作区状态（用于用户关闭工作区时）
        
        Returns:
            (success, message)
        """
        try:
            if self.state_file.exists():
                old_path = self.state_file.with_suffix(".json.bak")
                if old_path.exists():
                    old_path.unlink()
                shutil.copy2(self.state_file, old_path)
                self.state_file.unlink()
            return True, "工作区状态已清除"
        except Exception as e:
            return False, f"清除工作区状态失败: {e}"
    
    def get_workspace_info(self) -> Dict[str, Any]:
        """获取工作区详细信息
        
        此方法直接读取状态文件，获取完整的状态信息，
        包括原始保存的路径（即使路径已不存在）。
        
        Returns:
            包含工作区信息的字典：
            - is_saved: 状态文件是否存在且包含 workspace_path
            - saved_path: 原始保存的工作区路径（可能不存在）
            - workspace_path: 实际可用的工作区路径（不存在时为 None）
            - is_valid: 保存的路径是否仍然存在
            - workspace_name: 工作区名称（如果路径有效）
            - last_opened_at: 最后打开时间
            - state_file: 状态文件路径
            - state_file_exists: 状态文件是否存在
        """
        info = {
            "is_saved": False,
            "saved_path": None,
            "workspace_path": None,
            "is_valid": False,
            "workspace_name": None,
            "last_opened_at": None,
            "state_file": str(self.state_file),
            "state_file_exists": self.state_file.exists()
        }
        
        if not self.state_file.exists():
            return info
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = self._try_read_backup()
        
        saved_path = data.get("workspace_path")
        
        if saved_path:
            info["is_saved"] = True
            info["saved_path"] = saved_path
            info["last_opened_at"] = data.get("last_opened_at")
            
            workspace = Path(saved_path)
            if workspace.exists():
                info["is_valid"] = True
                info["workspace_path"] = saved_path
                info["workspace_name"] = workspace.name
            else:
                info["is_valid"] = False
                info["workspace_path"] = None
                info["workspace_name"] = None
        
        return info
    
    def _try_read_backup(self) -> Dict[str, Any]:
        """尝试从备份文件读取数据"""
        backup_file = self.state_file.with_suffix(".json.bak")
        if not backup_file.exists():
            return {}
        
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


# 全局工作区状态管理器实例
workspace_manager = WorkspaceStateManager()

NOTES_FOLDER = "Notes"
ORGANIZED_FOLDER = "Organized"
RAW_FOLDER = "Raw"
USED_FOLDER = "Used"

IGNORED_DIRS = {
    "ai",
    "wki",
    "wiki",
    "ai wiki",
    "ai-wiki",
    "ai_wiki",
    "aiwiki",
}


def _obfuscate(text: str) -> str:
    """对敏感文本做 base64 混淆（非加密，仅防止无意查看）"""
    return base64.b64encode(text.encode('utf-8')).decode('utf-8')


def _deobfuscate(text: str) -> str:
    """解混淆 base64 编码的文本"""
    try:
        return base64.b64decode(text.encode('utf-8')).decode('utf-8')
    except Exception:
        return text  # 兼容旧版本的明文存储


def _restrict_file_permissions(filepath: Path):
    """将文件权限设置为仅 owner 可读写 (600)"""
    try:
        os.chmod(filepath, 0o600)
    except Exception:
        pass


def is_ignored_dir(dir_name: str) -> bool:
    if not dir_name:
        return False
    return dir_name.lower() in IGNORED_DIRS

@dataclass
class AppConfig:
    """应用配置类"""
    # API配置
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 32000  # 32k tokens
    disable_thinking: bool = True

    # 全局上下文配置
    max_context_tokens: int = 128000  # 128k tokens，默认值

    # 工作文件夹配置
    workspace_path: str = ""

    log_path: str = str(Path.home() / "NoteAI" / "logs")
    
    # 处理配置
    batch_size: int = 5
    timeout: int = 30
    max_retries: int = 3
    
    # 内容处理配置
    max_content_length: int = 10000
    max_html_length: int = 15000
    max_chunk_length: int = 8000
    min_chunk_size: int = 200
    
    # 界面配置
    theme: str = "light"
    theme_preference: str = "system"
    accent_color: str = "#5B7DB1"
    window_width: int = 1400
    window_height: int = 900
    
    # 网页下载 AI 辅助开关（独立）
    web_ai_assist: bool = False
    
    # 网页下载图片开关（保留外部 URL 链接，不下载到本地）
    web_include_images: bool = False
    
    # 文件转换 AI 辅助开关（独立）
    conv_ai_assist: bool = False
    
    # 网页下载配置
    web_save_path: str = ""
    download_mode: str = "standard"
    
    # 文件转换配置
    conv_save_path: str = ""
    
    # 笔记整合配置
    integration_source_path: str = ""
    integration_output_path: str = ""
    integration_strategy: str = "ml"
    auto_topic: bool = True
    topic_list: str = ""
    
    def __post_init__(self):
        Path(self.log_path).mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _get_attr(self, name):
        with self._lock:
            return getattr(self, name, None)

    def _set_attr(self, name, value):
        with self._lock:
            setattr(self, name, value)

    def is_workspace_set(self) -> bool:
        """检查工作文件夹是否已设置"""
        if not self.workspace_path:
            return False
        return Path(self.workspace_path).exists()

    def get_notes_folder(self) -> str:
        """获取Notes子文件夹路径"""
        if not self.workspace_path:
            return ""
        return str(Path(self.workspace_path) / NOTES_FOLDER)

    def get_organized_folder(self) -> str:
        """获取Organized子文件夹路径"""
        if not self.workspace_path:
            return ""
        return str(Path(self.workspace_path) / ORGANIZED_FOLDER)

    def get_raw_folder(self) -> str:
        """获取Raw子文件夹路径"""
        if not self.workspace_path:
            return ""
        return str(Path(self.workspace_path) / RAW_FOLDER)

    def get_used_folder(self) -> str:
        """获取Used子文件夹路径"""
        if not self.workspace_path:
            return ""
        return str(Path(self.workspace_path) / USED_FOLDER)

    def setup_workspace_folders(self) -> Tuple[bool, str]:
        """
        创建工作文件夹的标准子文件夹（Notes、Organized和Raw）
        Returns:
            (success, message)
        """
        if not self.workspace_path:
            return False, "工作文件夹路径未设置"

        try:
            workspace = Path(self.workspace_path)
            if not workspace.exists():
                return False, f"工作文件夹不存在: {self.workspace_path}"

            notes_folder = workspace / NOTES_FOLDER
            organized_folder = workspace / ORGANIZED_FOLDER
            raw_folder = workspace / RAW_FOLDER

            notes_folder.mkdir(parents=True, exist_ok=True)
            organized_folder.mkdir(parents=True, exist_ok=True)
            raw_folder.mkdir(parents=True, exist_ok=True)

            return True, f"工作文件夹已设置: {self.workspace_path}"
        except PermissionError:
            return False, "创建文件夹失败：没有写入权限"
        except Exception as e:
            return False, f"创建文件夹失败：{str(e)}"

    def validate_api_config(self) -> bool:
        """验证API配置"""
        from utils.helpers import validate_api_key
        if not validate_api_key(self.api_key):
            return False
        if not self.api_base or not self.api_base.strip():
            return False
        if not self.model_name or not self.model_name.strip():
            return False
        if not (0.0 <= self.temperature <= 2.0):
            return False
        if self.max_tokens < 100 or self.max_tokens > 128000:
            return False
        return True
    
    def validate_context_config(self) -> bool:
        """验证上下文配置"""
        if self.max_context_tokens < 1000 or self.max_context_tokens > 1000000:
            return False
        return True
    
    def check_content_within_context(self, content: str) -> tuple:
        """
        检查内容是否在全局最大上下文限制内
        当超出限制时，采用LLM智能处理：
        1. 首先使用LLM进行摘要提取和智能压缩
        2. 若仍不满足，再进行有策略的内容截断
        
        Returns:
            (is_within_limit, estimated_tokens, processed_content)
        """
        from utils.helpers import _estimate_tokens
        estimated_tokens = _estimate_tokens(content, self.model_name)
        
        if estimated_tokens <= self.max_context_tokens:
            return (True, estimated_tokens, content)
        
        from utils.helpers import process_content_with_llm
        processed_content, was_summarized, was_truncated, final_tokens = process_content_with_llm(
            content,
            max_tokens=self.max_context_tokens,
            model_name=self.model_name
        )
        
        return (False, final_tokens, processed_content)
    
    @classmethod
    def _get_env_or_config(cls, env_var: str, config_value: Any, default: Any) -> Any:
        """从环境变量或配置值获取值，环境变量优先"""
        env_value = os.environ.get(env_var)
        if env_value is not None:
            return env_value
        if config_value is not None and config_value != "":
            return config_value
        return default

    @classmethod
    def load_from_file(cls, config_path: str = None) -> 'AppConfig':
        """从文件加载配置，环境变量优先"""
        if config_path is None:
            config_path = PROJECT_CONFIG_PATH

        file_data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
                print(f"加载配置失败: {e}, 使用默认配置")
            except Exception as e:
                print(f"加载配置时发生未知错误: {e}, 使用默认配置")

        api_data = {}
        if os.path.exists(API_CONFIG_FILE):
            try:
                with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    api_data = json.load(f)
                if 'api_key' in api_data and api_data['api_key']:
                    api_data['api_key'] = _deobfuscate(api_data['api_key'])
            except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
                print(f"加载API配置失败: {e}")
            except Exception as e:
                print(f"加载API配置时发生未知错误: {e}")

        env_mappings = {
            'api_key': ('NOTEAI_API_KEY', api_data.get('api_key', file_data.get('api_key', ''))),
            'api_base': ('NOTEAI_API_BASE', api_data.get('api_base', file_data.get('api_base', 'https://api.openai.com/v1'))),
            'model_name': ('NOTEAI_MODEL_NAME', api_data.get('model_name', file_data.get('model_name', 'gpt-4'))),
            'temperature': ('NOTEAI_TEMPERATURE', api_data.get('temperature', file_data.get('temperature', 0.7))),
            'max_tokens': ('NOTEAI_MAX_TOKENS', api_data.get('max_tokens', file_data.get('max_tokens', 32000))),
            'max_context_tokens': ('NOTEAI_MAX_CONTEXT', api_data.get('max_context_tokens', file_data.get('max_context_tokens', 128000))),
            'workspace_path': ('NOTEAI_WORKSPACE_PATH', file_data.get('workspace_path', '')),
        }

        init_kwargs = {}
        for key, (env_var, config_default) in env_mappings.items():
            env_value = os.environ.get(env_var)
            if env_value is not None:
                if key in ['temperature', 'max_tokens', 'max_context_tokens']:
                    try:
                        init_kwargs[key] = float(env_value) if '.' in env_value else int(env_value)
                    except ValueError:
                        init_kwargs[key] = config_default
                else:
                    init_kwargs[key] = env_value
            else:
                init_kwargs[key] = config_default

        for key, value in file_data.items():
            if key not in init_kwargs or init_kwargs[key] == '':
                init_kwargs[key] = value

        valid_keys = {f.name for f in fields(cls)}
        init_kwargs = {k: v for k, v in init_kwargs.items() if k in valid_keys}

        return cls(**init_kwargs)
    
    def save_to_file(self, config_path: str = None):
        """保存配置到文件，API相关配置仅保存到系统目录"""
        if config_path is None:
            config_path = PROJECT_CONFIG_PATH

        os.environ['NOTEAI_WORKSPACE_PATH'] = self.workspace_path
        os.environ['NOTEAI_API_BASE'] = self.api_base
        os.environ['NOTEAI_MODEL_NAME'] = self.model_name
        os.environ['NOTEAI_TEMPERATURE'] = str(self.temperature)
        os.environ['NOTEAI_MAX_TOKENS'] = str(self.max_tokens)
        os.environ['NOTEAI_MAX_CONTEXT'] = str(self.max_context_tokens)

        api_fields = {'api_key', 'api_base', 'model_name', 'temperature', 'max_tokens', 'max_context_tokens', 'disable_thinking'}
        _skip_keys = {'_lock'}

        try:
            Path(config_path).parent.mkdir(parents=True, exist_ok=True)

            non_api_config = {k: v for k, v in self.__dict__.items() if k not in api_fields and k not in _skip_keys}

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(non_api_config, f, ensure_ascii=False, indent=2)

            print(f"配置已保存到: {config_path}")
        except PermissionError:
            error_msg = "保存配置失败：没有写入权限"
            print(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"保存配置失败：{e}"
            print(error_msg)
            return False, error_msg

        try:
            SYSTEM_APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

            api_config = {k: v for k, v in self.__dict__.items() if k in api_fields}
            if 'api_key' in api_config and api_config['api_key']:
                api_config['api_key'] = _obfuscate(api_config['api_key'])

            with open(API_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(api_config, f, ensure_ascii=False, indent=2)

            _restrict_file_permissions(API_CONFIG_FILE)
            print(f"API配置已保存到: {API_CONFIG_FILE}")
        except PermissionError:
            print(f"保存API配置到系统目录失败：没有写入权限")
        except Exception as e:
            print(f"保存API配置到系统目录失败：{e}")

        return True, "配置保存成功"
    
    def save(self, config_path: str = None):
        """保存配置到文件（save_to_file 的别名，用于向后兼容）"""
        return self.save_to_file(config_path)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.__dict__.copy()

# 全局配置实例
config = AppConfig.load_from_file()
