import json
import os
import threading
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, Tuple

from .constants import (
    API_CONFIG_FILE,
    NOTES_FOLDER,
    ORGANIZED_FOLDER,
    PROJECT_CONFIG_PATH,
    RAW_FOLDER,
    SYSTEM_APP_DATA_DIR,
    USED_FOLDER,
)
from .security import _deobfuscate, _restrict_file_permissions


@dataclass
class AppConfig:
    NOTES_FOLDER: str = NOTES_FOLDER
    ORGANIZED_FOLDER: str = ORGANIZED_FOLDER
    RAW_FOLDER: str = RAW_FOLDER
    USED_FOLDER: str = USED_FOLDER

    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 32000
    disable_thinking: bool = True

    max_context_tokens: int = 128000

    workspace_path: str = ""
    log_path: str = str(SYSTEM_APP_DATA_DIR / "logs")

    batch_size: int = 5
    timeout: int = 30
    max_retries: int = 3

    max_content_length: int = 10000
    max_html_length: int = 15000
    max_chunk_length: int = 8000
    min_chunk_size: int = 200

    theme: str = "light"
    theme_preference: str = "system"
    accent_color: str = "#4A90D9"
    window_width: int = 1400
    window_height: int = 900

    web_ai_assist: bool = False
    web_include_images: bool = False
    conv_ai_assist: bool = False

    web_save_path: str = ""
    download_mode: str = "standard"
    conv_save_path: str = ""

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
        if not self.workspace_path:
            return False
        return Path(self.workspace_path).exists()

    def get_notes_folder(self) -> str:
        if not self.workspace_path:
            return ""
        return str(Path(self.workspace_path) / NOTES_FOLDER)

    def get_organized_folder(self) -> str:
        if not self.workspace_path:
            return ""
        return str(Path(self.workspace_path) / ORGANIZED_FOLDER)

    def get_raw_folder(self) -> str:
        if not self.workspace_path:
            return ""
        return str(Path(self.workspace_path) / RAW_FOLDER)

    def get_used_folder(self) -> str:
        if not self.workspace_path:
            return ""
        return str(Path(self.workspace_path) / USED_FOLDER)

    def setup_workspace_folders(self) -> Tuple[bool, str]:
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
        if self.max_context_tokens < 1000 or self.max_context_tokens > 1000000:
            return False
        return True

    def check_content_within_context(self, content: str) -> tuple:
        from utils.llm_utils import _estimate_tokens
        estimated_tokens = _estimate_tokens(content, self.model_name)

        if estimated_tokens <= self.max_context_tokens:
            return (True, estimated_tokens, content)

        from utils.llm_utils import process_content_with_llm
        processed_content, was_summarized, was_truncated, final_tokens = process_content_with_llm(
            content,
            max_tokens=self.max_context_tokens,
            model_name=self.model_name
        )

        return (False, final_tokens, processed_content)

    @classmethod
    def load_from_file(cls, config_path: str = None) -> 'AppConfig':
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
        api_key_from_file = None
        if os.path.exists(API_CONFIG_FILE):
            try:
                with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    api_data = json.load(f)
                if 'api_key' in api_data and api_data['api_key']:
                    api_key_from_file = _deobfuscate(api_data['api_key'])
            except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
                print(f"加载API配置失败: {e}")
            except Exception as e:
                print(f"加载API配置时发生未知错误: {e}")

        import importlib.util
        try:
            spec = importlib.util.find_spec("keyring")
            if spec:
                import keyring
                keyring_key = keyring.get_password("NoteAI", "api_key") or ""
            else:
                keyring_key = ""
        except Exception:
            keyring_key = ""
        if keyring_key:
            api_data['api_key'] = keyring_key
        elif api_key_from_file:
            api_data['api_key'] = api_key_from_file

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
                if key in ['temperature']:
                    try:
                        init_kwargs[key] = float(env_value)
                    except ValueError:
                        init_kwargs[key] = config_default
                elif key in ['max_tokens', 'max_context_tokens']:
                    try:
                        init_kwargs[key] = int(float(env_value))
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

    def save_to_file(self, config_path: str = None) -> Tuple[bool, str]:
        if not config_path:
            config_path = PROJECT_CONFIG_PATH

        os.environ['NOTEAI_WORKSPACE_PATH'] = self.workspace_path
        os.environ['NOTEAI_API_BASE'] = self.api_base
        os.environ['NOTEAI_MODEL_NAME'] = self.model_name
        os.environ['NOTEAI_TEMPERATURE'] = str(self.temperature)
        os.environ['NOTEAI_MAX_TOKENS'] = str(self.max_tokens)
        os.environ['NOTEAI_MAX_CONTEXT'] = str(self.max_context_tokens)
        # NOTE: API key is intentionally NOT written to environ — children
        # should obtain it from the keyring or api_config.json, not inherit it.

        api_fields = {'api_key', 'api_base', 'model_name', 'temperature', 'max_tokens', 'max_context_tokens', 'disable_thinking'}
        _skip_keys = {'_lock'}

        with self._lock:
            snapshot = dict(self.__dict__)

        try:
            Path(config_path).parent.mkdir(parents=True, exist_ok=True)

            non_api_config = {k: v for k, v in snapshot.items() if k not in api_fields and k not in _skip_keys}

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

        api_save_ok = True
        try:
            SYSTEM_APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

            api_config = {k: v for k, v in snapshot.items() if k in api_fields}
            if 'api_key' in api_config and api_config['api_key']:
                from utils.keyring_store import store_api_key
                store_api_key(api_config['api_key'])
                api_config.pop('api_key', None)

            if api_config:
                with open(API_CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(api_config, f, ensure_ascii=False, indent=2)

                _restrict_file_permissions(API_CONFIG_FILE)
            print(f"API配置已保存到: {API_CONFIG_FILE}")
        except PermissionError:
            api_save_ok = False
            print(f"保存API配置到系统目录失败：没有写入权限")
        except Exception as e:
            api_save_ok = False
            print(f"保存API配置到系统目录失败：{e}")

        if not api_save_ok:
            return True, "主配置已保存，但API配置保存失败"
        return True, "配置保存成功"

    def save(self, config_path: str = None):
        return self.save_to_file(config_path)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            d = self.__dict__.copy()
            d.pop('_lock', None)
            return d


config = AppConfig.load_from_file()