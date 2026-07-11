"""Cloud sync entrypoint.

The product keeps the settings entry visible, but sync execution is disabled
until conflict handling and provider UX are ready.
"""

from sidecar.handlers.base import BaseHandler

_DISABLED_MESSAGE = "云同步暂未开放，入口保留为实验功能占位。"


class CloudSyncHandler(BaseHandler):
    def register_routes(self, router):
        router.register("cloud_sync_list_providers", self._list_providers)
        router.register("cloud_sync_auth", self._disabled)
        router.register("cloud_sync_push", self._disabled)
        router.register("cloud_sync_pull", self._disabled)
        router.register("cloud_sync_status", self._disabled)
        router.register("cloud_sync_save_config", self._disabled)
        router.register("cloud_sync_load_config", self._disabled)
        router.register("cloud_sync_disconnect", self._disabled)

    def _list_providers(self, _params):
        return {
            "success": True,
            "enabled": False,
            "providers": [],
            "message": _DISABLED_MESSAGE,
        }

    def _disabled(self, _params):
        return {"success": False, "enabled": False, "message": _DISABLED_MESSAGE}
