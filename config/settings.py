import os
from pathlib import Path
from dataclasses import dataclass, field, fields
from typing import Optional, Dict, Any, Tuple
import json
from pydantic import BaseModel, Field, validator

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
# 项目配置文件路径
PROJECT_CONFIG_PATH = str(Path(__file__).parent / "config.json")

NOTES_FOLDER = "Notes"
ORGANIZED_FOLDER = "Organized"
RAW_FOLDER = "Raw"

@dataclass
class AppConfig:
    """应用配置类"""
    # API配置
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 32000  # 32k tokens

    # 全局上下文配置
    max_context_tokens: int = 128000  # 128k tokens，默认值

    # 工作文件夹配置
    workspace_path: str = ""

    # 路径配置
    default_save_path: str = str(Path.home() / "NoteAI" / "notes")
    temp_path: str = str(Path.home() / "NoteAI" / "temp")
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
    
    # 用户界面状态配置
    # 网页下载 AI 辅助开关（独立）
    web_ai_assist: bool = False
    
    # 网页下载图片开关
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
        # 确保目录存在
        Path(self.default_save_path).mkdir(parents=True, exist_ok=True)
        Path(self.temp_path).mkdir(parents=True, exist_ok=True)
        Path(self.log_path).mkdir(parents=True, exist_ok=True)

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
        try:
            import tiktoken
            encoding = tiktoken.encoding_for_model(self.model_name)
            estimated_tokens = len(encoding.encode(content))
        except Exception:
            estimated_tokens = len(content) // 4
        
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

        env_mappings = {
            'api_key': ('NOTEAI_API_KEY', file_data.get('api_key', '')),
            'api_base': ('NOTEAI_API_BASE', file_data.get('api_base', 'https://api.openai.com/v1')),
            'model_name': ('NOTEAI_MODEL_NAME', file_data.get('model_name', 'gpt-4')),
            'temperature': ('NOTEAI_TEMPERATURE', file_data.get('temperature', 0.7)),
            'max_tokens': ('NOTEAI_MAX_TOKENS', file_data.get('max_tokens', 32000)),
            'max_context_tokens': ('NOTEAI_MAX_CONTEXT', file_data.get('max_context_tokens', 128000)),
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
        """保存配置到文件"""
        if config_path is None:
            config_path = PROJECT_CONFIG_PATH

        os.environ['NOTEAI_WORKSPACE_PATH'] = self.workspace_path
        os.environ['NOTEAI_API_KEY'] = self.api_key
        os.environ['NOTEAI_API_BASE'] = self.api_base
        os.environ['NOTEAI_MODEL_NAME'] = self.model_name
        os.environ['NOTEAI_TEMPERATURE'] = str(self.temperature)
        os.environ['NOTEAI_MAX_TOKENS'] = str(self.max_tokens)
        os.environ['NOTEAI_MAX_CONTEXT'] = str(self.max_context_tokens)

        try:
            Path(config_path).parent.mkdir(parents=True, exist_ok=True)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.__dict__, f, ensure_ascii=False, indent=2)

            print(f"配置已保存到: {config_path}")
            return True, "配置保存成功"
        except PermissionError:
            error_msg = "保存配置失败：没有写入权限"
            print(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"保存配置失败：{e}"
            print(error_msg)
            return False, error_msg
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.__dict__.copy()

# 全局配置实例
config = AppConfig.load_from_file()
