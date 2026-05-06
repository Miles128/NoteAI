"""API / UI / theme + connectivity test (from python/main.py)."""

import json
import re
import sys
import shutil
import threading
from pathlib import Path

import yaml
from config import config, is_ignored_dir
from utils.helpers import test_api_connection

class ConfigMixin:
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
            "disable_thinking": config.disable_thinking,
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
        config.disable_thinking = params.get("disable_thinking", True)

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
