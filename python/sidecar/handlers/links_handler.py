from sidecar.handlers.base import BaseHandler
from utils.link_indexer import confirm_all_links, confirm_link, get_backlinks, load_links, reject_link


class LinksHandler(BaseHandler):
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

    def register_routes(self, router):
        router.register("get_backlinks", self._get_backlinks)
        router.register("get_link_stats", self._get_link_stats)
        router.register("confirm_link", self._confirm_link)
        router.register("reject_link", self._reject_link)
        router.register("confirm_all_links", self._confirm_all_links)
