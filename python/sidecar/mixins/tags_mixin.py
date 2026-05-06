"""Tag index, auto-tag, tags.md, tag CRUD (from python/main.py)."""

import json
import re
import sys
import shutil
import threading
from pathlib import Path

import yaml
from config import config, is_ignored_dir

class TagsMixin:
    def _get_all_tags(self, params):
        return self._cached_or_compute("all_tags", self._compute_all_tags)

    def _compute_all_tags(self):
        workspace = config.workspace_path
        if not workspace:
            return {"tags": []}

        import re
        tag_map = {}

        def _scan_dir(path):
            try:
                for entry in sorted(Path(path).iterdir(), key=lambda p: p.name.lower()):
                    if entry.name.startswith('.'):
                        continue
                    if entry.is_dir():
                        if is_ignored_dir(entry.name):
                            continue
                        _scan_dir(str(entry))
                    elif entry.suffix.lower() == '.md':
                        try:
                            text = entry.read_text(encoding='utf-8')
                            meta, _body = self._parse_frontmatter(text)
                            if meta is None:
                                continue
                            tags = meta.get('tags', [])
                            if isinstance(tags, str):
                                tags = [t.strip() for t in tags.split(',') if t.strip()]
                            elif not isinstance(tags, list):
                                continue
                            rel = str(entry.relative_to(workspace))
                            for tag in tags:
                                tag = str(tag).strip()
                                if tag:
                                    if tag not in tag_map:
                                        tag_map[tag] = []
                                    tag_map[tag].append(rel)
                        except Exception as e:
                            sys.stderr.write(f"[get_all_tags] error reading {entry}: {e}\n")
                            sys.stderr.flush()
            except PermissionError:
                pass

        _scan_dir(workspace)

        tags_md_path = Path(workspace) / 'tags.md'
        if tags_md_path.exists():
            try:
                text = tags_md_path.read_text(encoding='utf-8')
                for line in text.split('\n'):
                    if line.startswith('## '):
                        tag = line[3:].strip()
                        if tag and tag not in tag_map:
                            tag_map[tag] = []
            except Exception:
                pass

        sorted_tags = sorted(tag_map.items(), key=lambda x: -len(x[1]))
        return {"tags": [{"name": t, "count": len(f), "files": f} for t, f in sorted_tags]}
    def _auto_tag_files(self, params):
        """从已有标签名匹配文件名，为匹配到的 .md 文件批量添加标签。

        支持 dry_run 模式（params.get('dry_run') == True），仅返回预览而不实际修改文件。
        """
        import re
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        dry_run = params.get("dry_run", False)

        # Step 1: 收集所有现有标签名
        tag_map = {}
        for md_file in Path(workspace).rglob('*.md'):
            if md_file.name.startswith('.') or md_file.name.lower() in ('wiki.md', 'tags.md'):
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                meta, _ = self._parse_frontmatter(text)
                if meta is None:
                    continue
                tags = meta.get('tags', [])
                if isinstance(tags, str):
                    tags = [t.strip().strip("'\"") for t in tags.split(',') if t.strip()]
                elif not isinstance(tags, list):
                    continue
                for tag in tags:
                    if tag not in tag_map:
                        tag_map[tag] = []
            except Exception:
                pass

        if not tag_map:
            return {"success": True, "updated": 0, "preview": [], "message": "未找到已有标签"}

        all_tag_names = list(tag_map.keys())

        # Step 2: 扫描需要修改的文件，收集变更信息
        changes = []  # [{path, matched_tags, new_tags}]

        for entry in Path(workspace).iterdir():
            if not entry.is_dir() or entry.name.startswith('.'):
                continue
            if is_ignored_dir(entry.name):
                continue
            for md_file in entry.glob('*.md'):
                try:
                    text = md_file.read_text(encoding='utf-8')
                    fname = md_file.stem
                    matched_tags = [t for t in all_tag_names if t.lower() in fname.lower()]
                    if not matched_tags:
                        continue

                    had_bom = text.startswith('\ufeff')
                    clean = text.lstrip('\ufeff')
                    m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', clean)
                    if m:
                        yaml_text = m.group(2)
                        existing_tags = set()
                        for i, line in enumerate(yaml_text.split('\n')):
                            idx = line.find(':')
                            if idx < 0:
                                continue
                            key = line[:idx].strip()
                            val = line[idx + 1:].strip()
                            if key == 'tags':
                                if val.startswith('[') and val.endswith(']'):
                                    existing_tags = set(t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip())
                                break

                        new_tags = [t for t in matched_tags if t not in existing_tags]
                        if not new_tags:
                            continue

                        changes.append({
                            "path": str(md_file.relative_to(workspace)),
                            "existing_tags": sorted(existing_tags),
                            "matched_tags": matched_tags,
                            "new_tags_to_add": new_tags,
                        })
                    else:
                        changes.append({
                            "path": str(md_file.relative_to(workspace)),
                            "existing_tags": [],
                            "matched_tags": matched_tags,
                            "new_tags_to_add": matched_tags,
                        })
                except Exception as e:
                    sys.stderr.write(f"[auto_tag] error scanning {md_file}: {e}\n")
                    sys.stderr.flush()

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "updated": 0,
                "preview": changes,
                "message": f"预览：{len(changes)} 个文件将被修改"
            }

        # Step 3: 实际写入
        updated = 0
        for ch in changes:
            rel_path = Path(ch["path"])
            md_file = Path(workspace) / rel_path
            if not md_file.exists():
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                fname = md_file.stem
                had_bom = text.startswith('\ufeff')
                clean = text.lstrip('\ufeff')
                m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', clean)
                if m:
                    yaml_text = m.group(2)
                    existing_tags = set(ch["existing_tags"])
                    tags_line_idx = None
                    lines = yaml_text.split('\n')
                    for i, line in enumerate(lines):
                        idx = line.find(':')
                        if idx < 0:
                            continue
                        key = line[:idx].strip()
                        if key == 'tags':
                            tags_line_idx = i
                            break

                    new_tags = ch["new_tags_to_add"]
                    all_tags = list(existing_tags) + new_tags
                    new_tags_str = '[' + ', '.join(all_tags) + ']'

                    prefix = '\ufeff' if had_bom else ''
                    if tags_line_idx is not None:
                        lines[tags_line_idx] = 'tags: ' + new_tags_str
                        new_yaml = '\n'.join(lines)
                        new_text = prefix + m.group(1) + new_yaml + m.group(3) + clean[m.end():]
                    else:
                        new_yaml = yaml_text + '\ntags: ' + new_tags_str
                        new_text = prefix + m.group(1) + new_yaml + m.group(3) + clean[m.end():]

                    md_file.write_text(new_text, encoding='utf-8')
                    updated += 1
                else:
                    new_tags_str = '[' + ', '.join(ch["matched_tags"]) + ']'
                    frontmatter = '---\ntags: ' + new_tags_str + '\n---\n'
                    new_text = frontmatter + text
                    md_file.write_text(new_text, encoding='utf-8')
                    updated += 1
            except Exception as e:
                sys.stderr.write(f"[auto_tag] error writing {md_file}: {e}\n")
                sys.stderr.flush()

        return {
            "success": True,
            "updated": updated,
            "preview": changes,
        }
    def _save_tags_md(self, params):
        from utils.tag_extractor import save_tags_md
        return save_tags_md(config.workspace_path)

    def _ensure_tags_md(self, params):
        from utils.tag_extractor import save_tags_md
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
        workspace_path = Path(workspace)
        tags_md_path = workspace_path / 'tags.md'
        
        existing_tags = set()
        if tags_md_path.exists():
            try:
                text = tags_md_path.read_text(encoding='utf-8')
                for line in text.split('\n'):
                    if line.startswith('## '):
                        t = line[3:].strip()
                        if t:
                            existing_tags.add(t)
            except Exception:
                pass
        
        if tag_name in existing_tags:
            return {"success": True, "message": "标签已存在", "created": False}
        
        if tags_md_path.exists():
            try:
                text = tags_md_path.read_text(encoding='utf-8')
                if not text.endswith('\n'):
                    text += '\n'
                text += '\n## ' + tag_name + '\n'
                tags_md_path.write_text(text, encoding='utf-8')
            except Exception as e:
                return {"success": False, "message": f"写入 tags.md 失败: {e}"}
        else:
            from utils.tag_extractor import save_tags_md
            save_tags_md(workspace)
            if tags_md_path.exists():
                try:
                    text = tags_md_path.read_text(encoding='utf-8')
                    if not text.endswith('\n'):
                        text += '\n'
                    text += '\n## ' + tag_name + '\n'
                    tags_md_path.write_text(text, encoding='utf-8')
                except Exception:
                    pass
        
        return {"success": True, "message": f"已创建标签「{tag_name}」", "created": True}

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

        workspace_path = Path(workspace)

        existing_tags = set()
        for md_file in workspace_path.rglob('*.md'):
            if md_file.name.startswith('.') or md_file.name.lower() in ('wiki.md', 'tags.md'):
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
                if not m:
                    continue
                yaml_text = m.group(1)
                for line in yaml_text.split('\n'):
                    idx = line.find(':')
                    if idx < 0:
                        continue
                    key = line[:idx].strip()
                    val = line[idx + 1:].strip()
                    if key == 'tags':
                        if val.startswith('[') and val.endswith(']'):
                            tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
                            for t in tags:
                                existing_tags.add(t)
                        elif val:
                            existing_tags.add(val.strip().strip("'\""))
            except Exception:
                pass

        new_tag_exists = False
        for t in existing_tags:
            if t.lower() == new_tag.lower() and t != new_tag:
                new_tag = t
                new_tag_exists = True
                break
            elif t == new_tag:
                new_tag_exists = True
                break

        updated_count = 0

        for md_file in workspace_path.rglob('*.md'):
            if md_file.name.startswith('.') or md_file.name.lower() in ('wiki.md', 'tags.md'):
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                had_bom = text.startswith('\ufeff')
                meta, body = self._parse_frontmatter(text)
                if meta is None:
                    continue

                tags = meta.get('tags', [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(',') if t.strip()]
                if not isinstance(tags, list):
                    continue

                changed = False
                new_tags = []
                for t in tags:
                    t = str(t).strip()
                    if t == old_tag:
                        if new_tag not in new_tags:
                            new_tags.append(new_tag)
                        changed = True
                    else:
                        if t not in new_tags:
                            new_tags.append(t)

                if changed:
                    meta['tags'] = new_tags
                    import yaml as _yaml
                    new_fm = _yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
                    prefix = '\ufeff' if had_bom else ''
                    new_content = prefix + '---\n' + new_fm + '\n---\n' + body.lstrip('\n')
                    md_file.write_text(new_content, encoding='utf-8')
                    updated_count += 1
            except Exception:
                pass

        from utils.tag_extractor import save_tags_md
        save_tags_md(workspace)

        from utils.topic_assigner import sync_wiki_with_files
        sync_wiki_with_files()

        merged = new_tag_exists
        if merged:
            return {
                "success": True,
                "message": f"已合并标签到「{new_tag}」，更新 {updated_count} 个文件",
                "updated": updated_count,
                "merged": True
            }

        return {
            "success": True,
            "message": f"已重命名标签，更新 {updated_count} 个文件",
            "updated": updated_count,
            "merged": False
        }

    def _delete_tag(self, params):
        tag_name = params.get("tag_name", "")
        if not tag_name:
            return {"success": False, "message": "标签名不能为空"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        workspace_path = Path(workspace)
        updated_count = 0

        for md_file in workspace_path.rglob('*.md'):
            if md_file.name.startswith('.') or md_file.name.lower() in ('wiki.md', 'tags.md'):
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                had_bom = text.startswith('\ufeff')
                meta, body = self._parse_frontmatter(text)
                if meta is None:
                    continue

                tags = meta.get('tags', [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(',') if t.strip()]
                if not isinstance(tags, list):
                    continue

                filtered = [t for t in tags if str(t).strip() != tag_name]
                if len(filtered) != len(tags):
                    if filtered:
                        meta['tags'] = filtered
                        import yaml as _yaml
                        new_fm = _yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
                        prefix = '\ufeff' if had_bom else ''
                        new_content = prefix + '---\n' + new_fm + '\n---\n' + body.lstrip('\n')
                    else:
                        # 删除整个 tags 字段
                        meta.pop('tags', None)
                        if meta:
                            import yaml as _yaml
                            new_fm = _yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
                            prefix = '\ufeff' if had_bom else ''
                            new_content = prefix + '---\n' + new_fm + '\n---\n' + body.lstrip('\n')
                        else:
                            # 没有其他 frontmatter 字段，移除整个 frontmatter
                            prefix = '\ufeff' if had_bom else ''
                            new_content = prefix + body.lstrip('\n')
                    md_file.write_text(new_content, encoding='utf-8')
                    updated_count += 1
            except Exception:
                pass

        from utils.tag_extractor import save_tags_md
        save_tags_md(workspace)

        from utils.topic_assigner import sync_wiki_with_files
        sync_wiki_with_files()

        return {
            "success": True,
            "message": f"已删除标签「{tag_name}」，更新 {updated_count} 个文件",
            "updated": updated_count
        }
