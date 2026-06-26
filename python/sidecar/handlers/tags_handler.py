from pathlib import Path

import yaml

from config import config, is_ignored_dir
from sidecar.handlers.base import BaseHandler
from utils.logger import logger
from utils.tag_extractor import save_tags_md

IGNORED_TAG_FILES = {"WIKI.md", "tags.md"}


def _iter_markdown_files(workspace: str):
    workspace_path = Path(workspace)
    for md_file in sorted(workspace_path.rglob("*.md")):
        if md_file.name.startswith(".") or md_file.name in IGNORED_TAG_FILES:
            continue
        rel_parts = md_file.relative_to(workspace_path).parts
        if any(part.startswith(".") or part == "wiki" or is_ignored_dir(part) for part in rel_parts):
            continue
        yield md_file


def _normalize_tags(raw_tags) -> list[str]:
    if isinstance(raw_tags, str):
        value = raw_tags.strip()
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1]
        items = value.split(",")
    elif isinstance(raw_tags, list):
        items = raw_tags
    else:
        return []

    tags = []
    for item in items:
        tag = str(item).strip().strip("'\"")
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _dump_frontmatter(meta: dict, body: str, had_bom: bool) -> str:
    from sidecar.textutils import write_frontmatter

    return write_frontmatter(meta, body, had_bom=had_bom)


class TagsHandler(BaseHandler):
    def _get_all_tags(self, _params):
        return self._cached_or_compute("all_tags", self._compute_all_tags)

    def _compute_all_tags(self):
        workspace = config.workspace_path
        if not workspace:
            return {"tags": []}

        tag_map = self._collect_tag_map(workspace)
        sorted_tags = sorted(tag_map.items(), key=lambda x: -len(x[1]))
        return {"tags": [{"name": t, "count": len(f), "files": f} for t, f in sorted_tags]}

    def _auto_tag_files(self, params):
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        dry_run = params.get("dry_run", False)

        tag_map = self._collect_tag_map(workspace)
        if not tag_map:
            return {"success": True, "updated": 0, "preview": [], "message": "未找到已有标签"}

        all_tag_names = list(tag_map.keys())
        changes = self._build_auto_tag_changes(workspace, all_tag_names)

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "updated": 0,
                "preview": changes,
                "message": f"预览：{len(changes)} 个文件将被修改",
            }

        updated = 0
        for ch in changes:
            md_file = Path(workspace) / ch["path"]
            new_tags = [*ch["existing_tags"], *ch["new_tags_to_add"]]
            if self._write_tags(md_file, new_tags):
                updated += 1

        return {
            "success": True,
            "updated": updated,
            "preview": changes,
        }

    def _save_tags_md(self, _params):
        return save_tags_md(config.workspace_path)

    def _ensure_tags_md(self, _params):
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}
        return save_tags_md(workspace)

    def _create_tag(self, params):
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        tag_name = params.get("name", "")
        if not tag_name or not tag_name.strip():
            return {"success": False, "message": "标签名不能为空"}

        tag_name = tag_name.strip()
        existing_tags = set(self._collect_tag_map(workspace))

        if tag_name in existing_tags:
            return {"success": True, "message": "标签已存在", "created": False}

        return {
            "success": True,
            "message": f"标签「{tag_name}」已就绪，可通过编辑文件 frontmatter 使用",
            "created": True,
        }

    def _rename_tag(self, params):
        old_tag = params.get("old_tag", "")
        new_tag = params.get("new_tag", "")
        if not old_tag or not new_tag:
            return {"success": False, "message": "标签名不能为空"}
        if old_tag == new_tag:
            return {"success": True, "message": "标签名相同", "updated": 0}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        existing_tags = set(self._collect_tag_map(workspace))
        canonical_new_tag = self._canonical_existing_tag(existing_tags, new_tag)
        new_tag_exists = canonical_new_tag is not None
        if canonical_new_tag:
            new_tag = canonical_new_tag

        updated_count = 0
        for md_file in _iter_markdown_files(workspace):
            current_tags = self._read_tags(md_file)
            if old_tag not in current_tags:
                continue
            renamed_tags = self._rename_tags(current_tags, old_tag, new_tag)
            if self._write_tags(md_file, renamed_tags):
                updated_count += 1

        merged = new_tag_exists
        if merged:
            return {
                "success": True,
                "message": f"已合并标签到「{new_tag}」，更新 {updated_count} 个文件",
                "updated": updated_count,
                "merged": True,
            }

        return {
            "success": True,
            "message": f"已重命名标签，更新 {updated_count} 个文件",
            "updated": updated_count,
            "merged": False,
        }

    def _delete_tag(self, params):
        tag_name = params.get("tag_name", "")
        if not tag_name:
            return {"success": False, "message": "标签名不能为空"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        updated_count = 0

        for md_file in _iter_markdown_files(workspace):
            current_tags = self._read_tags(md_file)
            filtered = [tag for tag in current_tags if tag != tag_name]
            if len(filtered) == len(current_tags):
                continue
            if self._write_tags(md_file, filtered):
                updated_count += 1

        return {
            "success": True,
            "message": f"已删除标签「{tag_name}」，更新 {updated_count} 个文件",
            "updated": updated_count,
        }

    def _add_tag_to_file(self, params):
        file_path = params.get("file_path", "")
        tag = (params.get("tag") or "").strip()
        if not file_path:
            return {"success": False, "message": "未指定文件"}
        if not tag:
            return {"success": False, "message": "标签名不能为空"}

        full_path = self._resolve_path(file_path)
        if not full_path:
            return {"success": False, "message": "路径无效"}

        md_file = Path(full_path)
        if md_file.suffix.lower() != ".md":
            return {"success": False, "message": "只能给 Markdown 文件添加标签"}
        if not md_file.exists():
            return {"success": False, "message": "文件不存在"}

        current_tags = self._read_tags(md_file)
        if tag in current_tags:
            return {"success": True, "updated": False, "message": "标签已存在"}
        if not self._write_tags(md_file, [*current_tags, tag]):
            return {"success": False, "message": "写入标签失败"}
        self._invalidate_cache()
        return {"success": True, "updated": True, "message": f"已添加标签「{tag}」"}

    def _collect_tag_map(self, workspace: str) -> dict[str, list[str]]:
        tag_map = {}
        for md_file in _iter_markdown_files(workspace):
            try:
                rel = str(md_file.relative_to(workspace))
                for tag in self._read_tags(md_file):
                    tag_map.setdefault(tag, []).append(rel)
            except Exception as e:
                logger.warning(f"[tags] error reading {md_file}: {e}\n")
        return tag_map

    def _read_tags(self, md_file: Path) -> list[str]:
        text = md_file.read_text(encoding="utf-8")
        meta, _body = self._parse_frontmatter(text)
        if meta is None:
            return []
        return _normalize_tags(meta.get("tags", []))

    def _write_tags(self, md_file: Path, tags: list[str]) -> bool:
        if not md_file.exists():
            return False
        try:
            text = md_file.read_text(encoding="utf-8")
            had_bom = text.startswith("\ufeff")
            meta, body = self._parse_frontmatter(text)
            meta = dict(meta or {})
            old_tags = _normalize_tags(meta.get("tags", []))
            new_tags = _normalize_tags(tags)
            if old_tags == new_tags:
                return False
            if new_tags:
                meta["tags"] = new_tags
            else:
                meta.pop("tags", None)
            md_file.write_text(_dump_frontmatter(meta, body, had_bom), encoding="utf-8")
            return True
        except Exception as e:
            logger.warning(f"[tags] error writing {md_file}: {e}\n")
            return False

    def _build_auto_tag_changes(self, workspace: str, tag_names: list[str]) -> list[dict]:
        changes = []
        for md_file in _iter_markdown_files(workspace):
            matched_tags = [tag for tag in tag_names if tag.lower() in md_file.stem.lower()]
            if not matched_tags:
                continue
            existing_tags = self._read_tags(md_file)
            new_tags = [tag for tag in matched_tags if tag not in existing_tags]
            if not new_tags:
                continue
            changes.append(
                {
                    "path": str(md_file.relative_to(workspace)),
                    "existing_tags": existing_tags,
                    "matched_tags": matched_tags,
                    "new_tags_to_add": new_tags,
                }
            )
        return changes

    @staticmethod
    def _canonical_existing_tag(existing_tags: set[str], new_tag: str) -> str | None:
        for tag in existing_tags:
            if tag == new_tag or tag.lower() == new_tag.lower():
                return tag
        return None

    @staticmethod
    def _rename_tags(tags: list[str], old_tag: str, new_tag: str) -> list[str]:
        renamed_tags = []
        for tag in tags:
            replacement = new_tag if tag == old_tag else tag
            if replacement not in renamed_tags:
                renamed_tags.append(replacement)
        return renamed_tags

    def register_routes(self, router):
        router.register("get_all_tags", self._get_all_tags)
        router.register("auto_tag_files", self._auto_tag_files)
        router.register("save_tags_md", self._save_tags_md)
        router.register("ensure_tags_md", self._ensure_tags_md)
        router.register("create_tag", self._create_tag)
        router.register("rename_tag", self._rename_tag)
        router.register("delete_tag", self._delete_tag)
        router.register("add_tag_to_file", self._add_tag_to_file)
