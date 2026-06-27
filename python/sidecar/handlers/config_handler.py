from pathlib import Path

from sidecar.handlers.base import BaseHandler
from sidecar.rag.profile import load_profile, save_profile
from utils.llm_utils import test_api_connection
from utils.logger import logger


class ConfigHandler(BaseHandler):
    def register_routes(self, router):
        router.register("get_api_config", self._get_api_config)
        router.register("save_api_config", self._save_api_config)
        router.register("get_ui_config", self._get_ui_config)
        router.register("save_ui_config", self._save_ui_config)
        router.register("get_theme_preference", self._get_theme_preference)
        router.register("save_theme_preference", self._save_theme_preference)
        router.register("test_api_connection", self._test_api_connection)
        router.register("get_user_profile", self._get_user_profile)
        router.register("save_user_profile", self._save_user_profile)
        router.register("get_project_rules", self._get_project_rules)
        router.register("save_project_rules", self._save_project_rules)

    def _get_api_config(self, params):
        api_key = self.config.api_key or ""
        if len(api_key) > 12:
            masked = api_key[:4] + "■■■■" + api_key[-4:]
        elif api_key:
            masked = "■■■■"
        else:
            masked = ""
        return {
            "api_key": masked,
            "api_key_configured": bool(self.config.api_key),
            "api_base": self.config.api_base,
            "model_name": self.config.model_name,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "max_context_tokens": self.config.max_context_tokens,
            "disable_thinking": self.config.disable_thinking,
        }

    def _save_api_config(self, params):
        api_key = params.get("api_key", "")
        api_base = params.get("api_base", "https://api.openai.com/v1")
        model_name = params.get("model_name", "gpt-4")

        if "■■■■" in api_key:
            api_key = self.config._get_attr("api_key")

        if not api_key or not api_key.strip():
            return {"success": False, "message": "API Key 不能为空"}

        connected, conn_msg = test_api_connection(api_key, api_base, model_name)
        if not connected:
            return {"success": False, "message": conn_msg}

        # Apply all config changes under the config lock to keep the update atomic.
        with self.config._lock:
            self.config.api_key = api_key
            self.config.api_base = api_base
            self.config.model_name = model_name
            self.config.temperature = params.get("temperature", 0.7)
            self.config.max_tokens = params.get("max_tokens", 32000)
            self.config.max_context_tokens = params.get("max_context_tokens", 128000)
            self.config.disable_thinking = params.get("disable_thinking", True)

            save_ok, save_msg = self.config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True, "message": f"配置已保存，{conn_msg}"}

    def _get_ui_config(self, params):
        return {
            "web_ai_assist": self.config.web_ai_assist,
            "web_include_images": self.config.web_include_images,
            "conv_ai_assist": self.config.conv_ai_assist,
            "integration_strategy": self.config.integration_strategy,
            "auto_topic": self.config.auto_topic,
            "topic_list": self.config.topic_list,
            "font_size": self.config.font_size,
            "sidebar_font_family": self.config.sidebar_font_family,
            "preview_font_family": self.config.preview_font_family,
            "cloud_sync_experimental": self.config.cloud_sync_experimental,
            "assistant_agent_mode": self.config.assistant_agent_mode,
            "cli_agent_id": self.config.cli_agent_id,
            "rag_enabled": self.config.rag_enabled,
            "locale": self.config.locale,
        }

    def _save_ui_config(self, params):
        with self.config._lock:
            if "web_ai_assist" in params:
                self.config.web_ai_assist = params["web_ai_assist"]
            if "web_include_images" in params:
                self.config.web_include_images = params["web_include_images"]
            if "conv_ai_assist" in params:
                self.config.conv_ai_assist = params["conv_ai_assist"]
            if "integration_strategy" in params:
                self.config.integration_strategy = params["integration_strategy"]
            if "auto_topic" in params:
                self.config.auto_topic = params["auto_topic"]
            if "topic_list" in params:
                self.config.topic_list = params["topic_list"]
            if "font_size" in params:
                self.config.font_size = params["font_size"]
            if "sidebar_font_family" in params:
                self.config.sidebar_font_family = str(params["sidebar_font_family"] or "system")
            if "preview_font_family" in params:
                self.config.preview_font_family = str(params["preview_font_family"] or "system")
            if "cloud_sync_experimental" in params:
                self.config.cloud_sync_experimental = bool(params["cloud_sync_experimental"])
            if "assistant_agent_mode" in params:
                self.config.assistant_agent_mode = bool(params["assistant_agent_mode"])
            if "cli_agent_id" in params:
                self.config.cli_agent_id = str(params["cli_agent_id"] or "").strip()
            if "rag_enabled" in params:
                self.config.rag_enabled = bool(params["rag_enabled"])
            if "locale" in params:
                loc = str(params["locale"]).strip()
                self.config.locale = "en" if loc == "en" else "zh-CN"
            save_ok, save_msg = self.config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True, "message": "UI 配置已保存"}

    def _get_theme_preference(self, params):
        return self.config.theme_preference

    def _save_theme_preference(self, params):
        with self.config._lock:
            self.config.theme_preference = params.get("theme", "system")
            save_ok, save_msg = self.config.save()
        if not save_ok:
            return {"success": False, "message": save_msg}
        return {"success": True}

    def _test_api_connection(self, params):
        try:
            api_key = params.get("api_key", self.config.api_key or "")
            api_base = params.get("api_base", self.config.api_base or "https://api.openai.com/v1")
            model_name = params.get("model_name", self.config.model_name or "gpt-4")
            if "■■■■" in api_key:
                api_key = self.config.api_key
            connected, conn_msg = test_api_connection(api_key, api_base, model_name)
            if connected:
                return {"success": True, "message": conn_msg}
            return {"success": False, "message": conn_msg}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _get_user_profile(self, params):
        return {"success": True, "profile": load_profile()}

    def _save_user_profile(self, params):
        profile = load_profile()

        if "profile_md" in params:
            profile["profile_md"] = params["profile_md"]
            save_profile(profile)
            return {"success": True, "message": "用户画像已保存"}

        identity = profile.get("identity", {})
        if "profession" in params:
            identity["profession"] = params["profession"]
        if "expertise_areas" in params:
            identity["expertise_areas"] = params["expertise_areas"]
        if "interests" in params:
            identity["interests"] = params["interests"]
        if "learning_goals" in params:
            identity["learning_goals"] = params["learning_goals"]
        profile["identity"] = identity

        prefs = profile.get("preferences", {})
        if "answer_style" in params:
            prefs["answer_style"] = params["answer_style"]
        if "detail_level" in params:
            prefs["detail_level"] = params["detail_level"]
        profile["preferences"] = prefs

        save_profile(profile)
        return {"success": True, "message": "用户画像已保存"}

    def _get_project_rules(self, params):
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": True, "rules": ""}
        rules_path = Path(workspace) / ".ai_memory" / "project_rules.md"
        if rules_path.exists():
            try:
                return {"success": True, "rules": rules_path.read_text(encoding="utf-8")}
            except Exception as e:
                logger.error(f"[config_handler] reading project rules file: {e}")
        return {"success": True, "rules": ""}

    def _save_project_rules(self, params):
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}
        rules = params.get("rules", "")
        rules_path = Path(workspace) / ".ai_memory" / "project_rules.md"
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text(rules, encoding="utf-8")
        return {"success": True, "message": "项目规则已保存"}
