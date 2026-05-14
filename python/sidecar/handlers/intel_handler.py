import json
from pathlib import Path

import yaml
from config import config, is_ignored_dir
from sidecar.handlers.base import BaseHandler


class IntelHandler(BaseHandler):
    def _llm_rewrite(self, params):
        from utils.llm_utils import rewrite_with_llm, APIConfigError

        file_path = params.get("file_path", "")
        if not file_path:
            return {"success": False, "message": "未指定文件"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)
        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}

        try:
            content = full_path.read_text(encoding='utf-8')
            fm, body = self._parse_frontmatter(content)
            rewritten_body = rewrite_with_llm(body)
            if fm is not None:
                fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
                rewritten = '---\n' + fm_str + '\n---\n' + rewritten_body
            else:
                rewritten = rewritten_body
            full_path.write_text(rewritten, encoding='utf-8')
            return {"success": True, "message": "改写完成"}
        except APIConfigError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"改写失败: {str(e)}"}

    def _llm_rewrite_stream(self, params):
        from utils.llm_utils import rewrite_with_llm_stream, APIConfigError

        file_path = params.get("file_path", "")
        if not file_path:
            return {"success": False, "message": "未指定文件"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)
        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}

        try:
            content = full_path.read_text(encoding='utf-8')
            fm, body = self._parse_frontmatter(content)

            def on_chunk(token):
                self._send_response({
                    "id": "event",
                    "result": {
                        "type": "rewrite_chunk",
                        "file_path": file_path,
                        "token": token,
                    }
                })

            rewritten = rewrite_with_llm_stream(body, chunk_callback=on_chunk)

            self._send_response({
                "id": "event",
                "result": {
                    "type": "rewrite_done",
                    "file_path": file_path,
                    "success": True,
                    "rewritten_text": rewritten,
                }
            })
            return {"success": True, "message": "改写完成"}
        except APIConfigError as e:
            self._send_response({
                "id": "event",
                "result": {
                    "type": "rewrite_done",
                    "file_path": file_path,
                    "success": False,
                    "message": str(e),
                }
            })
            return {"success": False, "message": str(e)}
        except Exception as e:
            self._send_response({
                "id": "event",
                "result": {
                    "type": "rewrite_done",
                    "file_path": file_path,
                    "success": False,
                    "message": f"改写失败: {str(e)}",
                }
            })
            return {"success": False, "message": f"改写失败: {str(e)}"}

    def _llm_rewrite_apply(self, params):
        file_path = params.get("file_path", "")
        rewritten_text = params.get("rewritten_text", "")
        if not file_path:
            return {"success": False, "message": "未指定文件"}
        if not rewritten_text:
            return {"success": False, "message": "无改写内容"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)
        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}

        try:
            original = full_path.read_text(encoding='utf-8')
            from sidecar.textutils import parse_frontmatter
            fm, _ = parse_frontmatter(original)
            if fm is not None:
                fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
                final_text = f"---\n{fm_str}\n---\n\n{rewritten_text}"
            else:
                final_text = rewritten_text
            full_path.write_text(final_text, encoding='utf-8')
            return {"success": True, "message": "已保存"}
        except Exception as e:
            return {"success": False, "message": f"保存失败: {str(e)}"}

    def _search_files(self, params):
        query = params.get("query", "").strip()
        if not query:
            return {"success": True, "results": [], "query": "", "count": 0}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        workspace_path = Path(workspace)
        if not workspace_path.exists():
            return {"success": False, "message": "工作区不存在"}

        from utils.fulltext_index import fulltext_index

        raw_results = fulltext_index.search(query)
        results = []
        for item in raw_results:
            try:
                fpath = workspace_path / item["path"]
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue

            title = Path(item["path"]).stem
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("# ") and not stripped.startswith("## "):
                    title = stripped[2:].strip()
                    break

            results.append({
                "path": item["path"],
                "title": title,
                "snippet": item.get("snippet", ""),
                "name": Path(item["path"]).name,
                "matches": item.get("score", 0),
            })

        return {
            "success": True,
            "results": results,
            "query": query,
            "count": len(results),
        }

    def register_routes(self, router):
        router.register("llm_rewrite", self._llm_rewrite)
        router.register("llm_rewrite_stream", self._llm_rewrite_stream, async_mode=True)
        router.register("llm_rewrite_apply", self._llm_rewrite_apply)
        router.register("search_files", self._search_files)