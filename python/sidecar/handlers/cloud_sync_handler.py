import traceback

from sidecar.cloud.providers import ALL_PROVIDERS, PROVIDER_MAP
from sidecar.cloud.sync_engine import SyncEngine
from sidecar.handlers.base import BaseHandler
from utils.logger import logger


class CloudSyncHandler(BaseHandler):
    def register_routes(self, router):
        router.register("cloud_sync_list_providers", self._list_providers)
        router.register("cloud_sync_auth", self._auth)
        router.register("cloud_sync_push", self._push)
        router.register("cloud_sync_pull", self._pull)
        router.register("cloud_sync_status", self._status)
        router.register("cloud_sync_save_config", self._save_config)
        router.register("cloud_sync_load_config", self._load_config)
        router.register("cloud_sync_disconnect", self._disconnect)

    def _get_workspace(self):
        workspace = self.config.workspace_path
        if not workspace:
            return None
        return workspace

    def _list_providers(self, _params):
        providers = []
        workspace = self._get_workspace()
        for p in ALL_PROVIDERS:
            info = {
                "name": p.PROVIDER_NAME,
                "display_name": p.DISPLAY_NAME,
                "auth_type": p.AUTH_TYPE,
                "auth_fields": p.AUTH_FIELDS,
                "authenticated": False,
                "last_push": None,
                "last_pull": None,
            }
            if workspace:
                saved = SyncEngine.load_provider_config(workspace, p.PROVIDER_NAME)
                if saved:
                    try:
                        provider = SyncEngine.create_provider(p.PROVIDER_NAME, saved)
                        info["authenticated"] = provider.is_authenticated()
                    except Exception:
                        pass
                state = SyncEngine(workspace, SyncEngine.create_provider(p.PROVIDER_NAME, saved or {}))._load_state()
                info["last_push"] = state.get("last_push")
                info["last_pull"] = state.get("last_pull")
            providers.append(info)
        return {"success": True, "providers": providers}

    def _auth(self, params):
        workspace = self._get_workspace()
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}
        provider_name = params.get("provider_name", "")
        credentials = params.get("credentials", {})
        if not provider_name or provider_name not in PROVIDER_MAP:
            return {"success": False, "message": "无效的云存储服务"}
        try:
            saved = SyncEngine.load_provider_config(workspace, provider_name)
            merged = {**saved, **credentials}
            provider = SyncEngine.create_provider(provider_name, merged)
            result = provider.authenticate(credentials)
            if result.get("success"):
                SyncEngine.save_provider_config(workspace, provider_name, merged)
            return result
        except Exception as e:
            logger.warning(f"[cloud_sync] auth failed: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _resolve_provider(self, params):
        workspace = self._get_workspace()
        if not workspace:
            return None, {"success": False, "message": "请先设置工作区"}
        provider_name = params.get("provider_name", "")
        if not provider_name or provider_name not in PROVIDER_MAP:
            return None, {"success": False, "message": "无效的云存储服务"}
        saved = SyncEngine.load_provider_config(workspace, provider_name)
        if not saved:
            return None, {"success": False, "message": "请先认证云存储服务"}
        try:
            provider = SyncEngine.create_provider(provider_name, saved)
            if not provider.is_authenticated():
                return None, {"success": False, "message": "认证已过期，请重新认证"}
        except Exception as e:
            return None, {"success": False, "message": f"创建连接失败: {e}"}
        return provider, None

    def _push(self, params):
        provider, err = self._resolve_provider(params)
        if err:
            return err
        workspace = self._get_workspace()
        if not self._start_task("cloud_push", self._do_push, args=(workspace, provider)):
            return {"success": False, "message": "推送任务正在进行中，请稍后"}
        return {"success": True, "message": "推送已开始"}

    def _do_push(self, workspace, provider):
        try:
            engine = SyncEngine(workspace, provider)

            def progress_cb(current, total, message):
                self._send_progress("cloud-push-progress", current / total if total > 0 else 0, message)

            result = engine.push(progress_callback=progress_cb)
            self._send_response(
                {
                    "id": "event",
                    "result": {"type": "cloud_push_complete", "data": result},
                }
            )
        except Exception as e:
            logger.warning(f"[cloud_sync] push failed: {e}\n{traceback.format_exc()}")
            self._send_response(
                {
                    "id": "event",
                    "result": {"type": "cloud_push_error", "error": str(e)},
                }
            )

    def _pull(self, params):
        provider, err = self._resolve_provider(params)
        if err:
            return err
        workspace = self._get_workspace()
        if not self._start_task("cloud_pull", self._do_pull, args=(workspace, provider)):
            return {"success": False, "message": "拉取任务正在进行中，请稍后"}
        return {"success": True, "message": "拉取已开始"}

    def _do_pull(self, workspace, provider):
        try:
            engine = SyncEngine(workspace, provider)

            def progress_cb(current, total, message):
                self._send_progress("cloud-pull-progress", current / total if total > 0 else 0, message)

            result = engine.pull(progress_callback=progress_cb)
            self._send_response(
                {
                    "id": "event",
                    "result": {"type": "cloud_pull_complete", "data": result},
                }
            )
        except Exception as e:
            logger.warning(f"[cloud_sync] pull failed: {e}\n{traceback.format_exc()}")
            self._send_response(
                {
                    "id": "event",
                    "result": {"type": "cloud_pull_error", "error": str(e)},
                }
            )

    def _status(self, params):
        workspace = self._get_workspace()
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}
        provider_name = params.get("provider_name", "")
        if not provider_name or provider_name not in PROVIDER_MAP:
            return {"success": False, "message": "无效的云存储服务"}
        saved = SyncEngine.load_provider_config(workspace, provider_name)
        if not saved:
            return {
                "success": True,
                "data": {
                    "provider": provider_name,
                    "authenticated": False,
                    "local_file_count": 0,
                    "last_push": None,
                    "last_pull": None,
                },
            }
        try:
            provider = SyncEngine.create_provider(provider_name, saved)
            engine = SyncEngine(workspace, provider)
            return {"success": True, "data": engine.get_status()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _save_config(self, params):
        workspace = self._get_workspace()
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}
        provider_name = params.get("provider_name", "")
        config = params.get("config", {})
        if not provider_name or provider_name not in PROVIDER_MAP:
            return {"success": False, "message": "无效的云存储服务"}
        SyncEngine.save_provider_config(workspace, provider_name, config)
        return {"success": True, "message": "配置已保存"}

    def _load_config(self, params):
        workspace = self._get_workspace()
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}
        provider_name = params.get("provider_name", "")
        if not provider_name or provider_name not in PROVIDER_MAP:
            return {"success": False, "message": "无效的云存储服务"}
        config = SyncEngine.load_provider_config(workspace, provider_name)
        masked = {}
        for k, v in config.items():
            if "password" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                if isinstance(v, str) and len(v) > 8:
                    masked[k] = v[:4] + "****" + v[-4:]
                elif isinstance(v, str) and v:
                    masked[k] = "****"
                else:
                    masked[k] = v
            else:
                masked[k] = v
        return {"success": True, "config": masked}

    def _disconnect(self, params):
        workspace = self._get_workspace()
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}
        provider_name = params.get("provider_name", "")
        if not provider_name or provider_name not in PROVIDER_MAP:
            return {"success": False, "message": "无效的云存储服务"}
        SyncEngine.save_provider_config(workspace, provider_name, {})
        return {"success": True, "message": "已断开连接"}
