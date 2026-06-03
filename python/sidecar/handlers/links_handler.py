import threading

from sidecar.handlers.base import BaseHandler
from utils.link_indexer import confirm_all_links, confirm_link, discover_links, get_backlinks, load_links, reject_link


class LinksHandler(BaseHandler):
    def _discover_links(self, _params):
        if not self._link_discovery_lock.acquire(blocking=False):
            return {"success": False, "message": "链接发现正在进行中，请等待完成"}

        def run():
            def progress_callback(stage, total, message):
                self._send_progress("link-discovery-progress", int(stage / total * 100), message)

            try:
                result = discover_links(progress_callback=progress_callback)
            except Exception as e:
                result = {"success": False, "message": f"链接发现失败: {e}"}
            finally:
                self._link_discovery_lock.release()

            self._send_response({
                "id": "event",
                "result": {
                    "type": "link_discovery_complete",
                    "data": result,
                }
            })

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return {"success": True, "status": "started", "message": "链接发现已启动"}

    def _get_backlinks(self, params):
        file_path = params.get("file_path", "") or ""
        return get_backlinks(file_path)

    def _get_link_stats(self, _params):
        links = load_links().get("links", [])
        confirmed = sum(1 for link in links if link.get("status") == "confirmed")
        pending = sum(1 for link in links if link.get("status") == "pending")
        return {
            "success": True,
            "total": len(links),
            "confirmed": confirmed,
            "pending": pending,
        }

    def _confirm_link(self, params):
        from_path = params.get("from", "")
        to_path = params.get("to", "")
        if not from_path or not to_path:
            return {"success": False, "message": "参数不完整"}
        return confirm_link(from_path, to_path)

    def _reject_link(self, params):
        from_path = params.get("from", "")
        to_path = params.get("to", "")
        if not from_path or not to_path:
            return {"success": False, "message": "参数不完整"}
        return reject_link(from_path, to_path)

    def _confirm_all_links(self, _params):
        return confirm_all_links()

    def _discover_cross_refs_for_file(self, params):
        file_path = params.get("file_path", "")
        if not file_path:
            return {"success": False, "message": "未指定文件"}
        from utils.link_indexer import discover_cross_refs_for_file

        return discover_cross_refs_for_file(file_path)

    def register_routes(self, router):
        router.register("discover_links", self._discover_links)
        router.register("discover_cross_refs_for_file", self._discover_cross_refs_for_file)
        router.register("get_backlinks", self._get_backlinks)
        router.register("get_link_stats", self._get_link_stats)
        router.register("confirm_link", self._confirm_link)
        router.register("reject_link", self._reject_link)
        router.register("confirm_all_links", self._confirm_all_links)
