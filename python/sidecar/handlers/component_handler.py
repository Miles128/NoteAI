import threading

from config import config
from sidecar.handlers.base import BaseHandler
from utils.component_state import set_component_removed
from utils.logger import logger
from utils.package_manager import ensure_feature, list_components, uninstall_feature


class ComponentHandler(BaseHandler):
    _install_lock = threading.Lock()

    def register_routes(self, router):
        router.register("get_components_status", self._get_components_status)
        router.register("install_component", self._install_component)
        router.register("uninstall_component", self._uninstall_component)

    def _get_components_status(self, params):
        return {"success": True, "components": list_components()}

    def _install_component(self, params):
        component_id = str(params.get("id") or params.get("name") or "").strip()
        if not component_id:
            return {"success": False, "message": "缺少组件 id"}

        if not self._install_lock.acquire(blocking=False):
            return {"success": False, "message": "组件安装正在进行中"}

        def work():
            try:
                self._send_progress("component-install", 5, f"正在安装 {component_id}…")

                def _progress(msg: str, pct: int) -> None:
                    self._send_progress("component-install", pct, msg)

                ok, message = ensure_feature(component_id, show_progress=False)
                if ok:
                    set_component_removed(component_id, False)
                    _progress("安装完成", 100)
                    self._send_response(
                        {
                            "id": "event",
                            "result": {
                                "type": "component_installed",
                                "success": True,
                                "id": component_id,
                                "message": message,
                                "restart_required": True,
                            },
                        }
                    )
                else:
                    self._send_response(
                        {
                            "id": "event",
                            "result": {
                                "type": "component_installed",
                                "success": False,
                                "id": component_id,
                                "message": message,
                            },
                        }
                    )
            except Exception as e:
                logger.warning("[component_handler] install error: %s", e)
                self._send_response(
                    {
                        "id": "event",
                        "result": {
                            "type": "component_installed",
                            "success": False,
                            "id": component_id,
                            "message": str(e),
                        },
                    }
                )
            finally:
                self._install_lock.release()

        threading.Thread(target=work, daemon=True).start()
        return {"success": True, "status": "started"}

    def _uninstall_component(self, params):
        component_id = str(params.get("id") or params.get("name") or "").strip()
        if not component_id:
            return {"success": False, "message": "缺少组件 id"}

        ok, message = uninstall_feature(component_id)
        if not ok:
            return {"success": False, "message": message}

        set_component_removed(component_id, True)

        if component_id == "rag":
            with config._lock:
                config.rag_enabled = False
                save_ok, save_msg = config.save()
            if not save_ok:
                return {"success": False, "message": save_msg}

        return {
            "success": True,
            "message": "组件已删除",
            "restart_required": True,
            "components": list_components(),
        }
