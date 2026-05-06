"""LLM rewrite, search, AI topic consolidation (from python/main.py)."""

import json
import re
import sys
import shutil
import threading
from pathlib import Path

import yaml
from config import config, is_ignored_dir


class IntelMixin:
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
                import yaml
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

            rewritten = rewrite_with_llm_stream(content, chunk_callback=on_chunk)

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
            full_path.write_text(rewritten_text, encoding='utf-8')
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

        results = []
        query_lower = query.lower()

        for md_file in workspace_path.rglob('*.md'):
            if md_file.name.startswith('.'):
                continue
            if md_file.name.lower() in ('wiki.md', 'tags.md'):
                continue

            try:
                text = md_file.read_text(encoding='utf-8')
                text_lower = text.lower()

                if query_lower not in text_lower:
                    continue

                matches = text_lower.count(query_lower)
                rel_path = str(md_file.relative_to(workspace_path))

                title = md_file.stem
                for line in text.split('\n'):
                    stripped = line.strip()
                    if stripped.startswith('# ') and not stripped.startswith('## '):
                        title = stripped[2:].strip()
                        break

                snippet = ""
                idx = text_lower.find(query_lower)
                if idx >= 0:
                    start = max(0, idx - 40)
                    end = min(len(text), idx + len(query) + 80)
                    snippet = text[start:end].replace('\n', ' ')
                    if start > 0:
                        snippet = '...' + snippet
                    if end < len(text):
                        snippet = snippet + '...'

                results.append({
                    "path": rel_path,
                    "title": title,
                    "snippet": snippet,
                    "name": md_file.name,
                    "matches": matches
                })
            except Exception:
                continue

        results.sort(key=lambda r: -r["matches"])
        results = results[:50]

        return {
            "success": True,
            "results": results,
            "query": query,
            "count": len(results)
        }

    def _ai_topic_analyze(self, params):
        from utils.llm_utils import call_llm_raw, check_api_config, APIConfigError
        from prompts.ai_topic_consolidate import AI_TOPIC_ANALYZE_PROMPT

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        try:
            is_valid, error_msg = check_api_config()
            if not is_valid:
                return {"success": False, "message": error_msg}
        except APIConfigError as e:
            return {"success": False, "message": str(e)}

        headings = self._parse_wiki_headings()
        existing_topics = [h["name"] for h in headings if h["level"] == 2]

        workspace_path = Path(workspace)
        files_info = []
        for md_file in sorted(workspace_path.rglob('*.md')):
            if md_file.name.startswith('.'):
                continue
            if md_file.name.lower() in ('wiki.md', 'tags.md'):
                continue
            rel_path = str(md_file.relative_to(workspace_path))
            file_topic = ""
            content_summary = ""
            try:
                text = md_file.read_text(encoding='utf-8')
                fm, body = self._parse_frontmatter(text)
                if fm and isinstance(fm.get('topics'), list):
                    file_topic = ', '.join(fm['topics'])
                lines = body.strip().split('\n')
                summary_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped and not stripped.startswith('```') and not stripped.startswith('---'):
                        summary_lines.append(stripped)
                        if len(summary_lines) >= 5:
                            break
                content_summary = ' '.join(summary_lines)[:200]
            except Exception:
                pass
            files_info.append({
                "name": md_file.name,
                "path": rel_path,
                "topic": file_topic,
                "summary": content_summary,
            })

        file_list_str = '\n'.join([
            f"- {f['name']} (路径: {f['path']}, 当前主题: {f['topic'] or '无'}, 摘要: {f['summary'] or '无'})"
            for f in files_info
        ])
        existing_topics_str = '\n'.join(["- " + t for t in existing_topics]) if existing_topics else "暂无主题"

        prompt = AI_TOPIC_ANALYZE_PROMPT.format(
            existing_topics=existing_topics_str,
            file_list=file_list_str
        )

        try:
            result_text = call_llm_raw(prompt, temperature=0.3)
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if not json_match:
                return {"success": False, "message": "LLM 返回格式异常"}
            suggestions = json.loads(json_match.group())
            return {"success": True, "suggestions": suggestions.get("suggestions", [])}
        except APIConfigError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"分析失败: {str(e)}"}

    def _ai_topic_survey(self, params):
        from utils.llm_utils import rewrite_with_llm_stream, check_api_config, APIConfigError
        from prompts.topic_survey import TOPIC_SURVEY_PROMPT

        topic_name = params.get("topic", "")
        if not topic_name:
            return {"success": False, "message": "未指定主题"}

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        try:
            is_valid, error_msg = check_api_config()
            if not is_valid:
                return {"success": False, "message": error_msg}
        except APIConfigError as e:
            return {"success": False, "message": str(e)}

        workspace_path = Path(workspace)
        notes_parts = []
        for md_file in sorted(workspace_path.rglob('*.md')):
            if md_file.name.startswith('.'):
                continue
            if md_file.name.lower() in ('wiki.md', 'tags.md'):
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                fm, body = self._parse_frontmatter(text)
                if fm and isinstance(fm.get('topics'), list):
                    if topic_name in fm['topics']:
                        content = body.strip()[:2000]
                        if content:
                            notes_parts.append(f"### {md_file.name}\n\n{content}")
            except Exception:
                continue

        if not notes_parts:
            return {"success": False, "message": f"主题 \"{topic_name}\" 下没有找到任何文件"}

        notes_content = '\n\n---\n\n'.join(notes_parts)
        prompt = TOPIC_SURVEY_PROMPT.format(
            topic_name=topic_name,
            notes_content=notes_content
        )

        full_text = ""

        def on_chunk(token):
            self._send_response({
                "id": "event",
                "result": {
                    "type": "survey_chunk",
                    "topic": topic_name,
                    "token": token,
                }
            })

        try:
            from langchain_core.prompts import PromptTemplate
            from utils.llm_utils import _create_llm

            llm = _create_llm(temperature=0.3)
            pt = PromptTemplate(template=prompt, input_variables=[])
            chain = pt | llm

            for chunk in chain.stream({}):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                full_text += token
                on_chunk(token)

            survey_filename = f"{topic_name}_综述.md"
            survey_path = workspace_path / survey_filename
            survey_path.write_text(full_text.strip(), encoding='utf-8')

            self._send_response({
                "id": "event",
                "result": {
                    "type": "survey_done",
                    "topic": topic_name,
                    "success": True,
                    "file_path": survey_filename,
                }
            })
            return {"success": True, "message": "综述撰写完成", "file_path": survey_filename}
        except APIConfigError as e:
            self._send_response({
                "id": "event",
                "result": {
                    "type": "survey_done",
                    "topic": topic_name,
                    "success": False,
                    "message": str(e),
                }
            })
            return {"success": False, "message": str(e)}
        except Exception as e:
            self._send_response({
                "id": "event",
                "result": {
                    "type": "survey_done",
                    "topic": topic_name,
                    "success": False,
                    "message": f"撰写失败: {str(e)}",
                }
            })
            return {"success": False, "message": f"撰写失败: {str(e)}"}

    def _apply_topic_suggestion(self, params):
        from utils.topic_assigner import write_topic_to_file

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        suggestion = params.get("suggestion", {})
        stype = suggestion.get("type", "")

        workspace_path = Path(workspace)
        wiki_path = workspace_path / "WIKI.md"

        try:
            if stype == "new_topic":
                topic_name = suggestion.get("topic", "").strip()
                files = suggestion.get("files", [])
                if not topic_name:
                    return {"success": False, "message": "主题名不能为空"}

                wiki_text = ""
                if wiki_path.exists():
                    wiki_text = wiki_path.read_text(encoding='utf-8')

                if '## ' + topic_name not in wiki_text:
                    wiki_text += f'\n## {topic_name}\n'

                wiki_lines = wiki_text.split('\n')
                topic_idx = -1
                for i, line in enumerate(wiki_lines):
                    if line.strip() == f'## {topic_name}':
                        topic_idx = i
                        break

                existing_files = set()
                if topic_idx >= 0:
                    for line in wiki_lines[topic_idx + 1:]:
                        if line.strip().startswith('## '):
                            break
                        if line.strip().startswith('### '):
                            existing_files.add(line.strip()[4:].strip())

                insert_pos = topic_idx + 1
                for i in range(topic_idx + 1, len(wiki_lines)):
                    if wiki_lines[i].strip().startswith('## '):
                        insert_pos = i
                        break
                else:
                    insert_pos = len(wiki_lines)

                new_entries = []
                for fname in files:
                    fn = fname.strip()
                    if fn and fn not in existing_files:
                        new_entries.append(f'### {fn}')

                for j, entry in enumerate(new_entries):
                    wiki_lines.insert(insert_pos + j, entry)

                wiki_path.write_text('\n'.join(wiki_lines), encoding='utf-8')

                for fname in files:
                    fn = fname.strip()
                    if not fn:
                        continue
                    for md_file in workspace_path.rglob(fn):
                        if md_file.is_file():
                            write_topic_to_file(str(md_file), topic_name)

            elif stype == "change_topic":
                fname = suggestion.get("file", "").strip()
                new_topic = suggestion.get("suggested_topic", "").strip()
                old_topic = suggestion.get("current_topic", "").strip()
                if not fname or not new_topic:
                    return {"success": False, "message": "文件名或主题名不能为空"}

                wiki_text = ""
                if wiki_path.exists():
                    wiki_text = wiki_path.read_text(encoding='utf-8')

                if '## ' + new_topic not in wiki_text:
                    wiki_text += f'\n## {new_topic}\n'

                wiki_lines = wiki_text.split('\n')

                if old_topic:
                    old_idx = -1
                    for i, line in enumerate(wiki_lines):
                        if line.strip() == f'## {old_topic}':
                            old_idx = i
                            break
                    if old_idx >= 0:
                        for j in range(old_idx + 1, len(wiki_lines)):
                            if wiki_lines[j].strip().startswith('## '):
                                break
                            if wiki_lines[j].strip() == f'### {fname}':
                                wiki_lines.pop(j)
                                break

                new_idx = -1
                for i, line in enumerate(wiki_lines):
                    if line.strip() == f'## {new_topic}':
                        new_idx = i
                        break

                if new_idx >= 0:
                    already_exists = False
                    for line in wiki_lines[new_idx + 1:]:
                        if line.strip().startswith('## '):
                            break
                        if line.strip() == f'### {fname}':
                            already_exists = True
                            break
                    if not already_exists:
                        insert_pos = new_idx + 1
                        for i in range(new_idx + 1, len(wiki_lines)):
                            if wiki_lines[i].strip().startswith('## '):
                                insert_pos = i
                                break
                        else:
                            insert_pos = len(wiki_lines)
                        wiki_lines.insert(insert_pos, f'### {fname}')

                wiki_path.write_text('\n'.join(wiki_lines), encoding='utf-8')

                for md_file in workspace_path.rglob(fname):
                    if md_file.is_file():
                        write_topic_to_file(str(md_file), new_topic)

            elif stype == "assign_topic":
                fname = suggestion.get("file", "").strip()
                topic_name = suggestion.get("topic", "").strip()
                if not fname or not topic_name:
                    return {"success": False, "message": "文件名或主题名不能为空"}

                wiki_text = ""
                if wiki_path.exists():
                    wiki_text = wiki_path.read_text(encoding='utf-8')

                if '## ' + topic_name not in wiki_text:
                    wiki_text += f'\n## {topic_name}\n'

                wiki_lines = wiki_text.split('\n')
                topic_idx = -1
                for i, line in enumerate(wiki_lines):
                    if line.strip() == f'## {topic_name}':
                        topic_idx = i
                        break

                already_exists = False
                if topic_idx >= 0:
                    for line in wiki_lines[topic_idx + 1:]:
                        if line.strip().startswith('## '):
                            break
                        if line.strip() == f'### {fname}':
                            already_exists = True
                            break

                if not already_exists:
                    insert_pos = topic_idx + 1
                    for i in range(topic_idx + 1, len(wiki_lines)):
                        if wiki_lines[i].strip().startswith('## '):
                            insert_pos = i
                            break
                    else:
                        insert_pos = len(wiki_lines)
                    wiki_lines.insert(insert_pos, f'### {fname}')

                wiki_path.write_text('\n'.join(wiki_lines), encoding='utf-8')

                for md_file in workspace_path.rglob(fname):
                    if md_file.is_file():
                        write_topic_to_file(str(md_file), topic_name)

            elif stype == "merge_topic":
                source = suggestion.get("source_topic", "").strip()
                target = suggestion.get("target_topic", "").strip()
                if not source or not target:
                    return {"success": False, "message": "主题名不能为空"}

                wiki_text = ""
                if wiki_path.exists():
                    wiki_text = wiki_path.read_text(encoding='utf-8')

                lines = wiki_text.split('\n')
                new_lines = []
                moved_files = []
                in_source = False
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith('## '):
                        heading = stripped[3:].strip()
                        if heading == source:
                            in_source = True
                            continue
                        else:
                            in_source = False
                    if in_source:
                        if stripped.startswith('### '):
                            moved_files.append(stripped[4:].strip())
                        continue
                    new_lines.append(line)

                wiki_text = '\n'.join(new_lines)

                target_idx = -1
                for i, line in enumerate(wiki_text.split('\n')):
                    if line.strip() == f'## {target}':
                        target_idx = i
                        break

                if target_idx == -1:
                    wiki_text += f'\n## {target}\n'
                    for fname in moved_files:
                        wiki_text += f'\n### {fname}\n'
                else:
                    target_section_lines = wiki_text.split('\n')
                    existing_files = set()
                    for line in target_section_lines[target_idx + 1:]:
                        if line.strip().startswith('## '):
                            break
                        if line.strip().startswith('### '):
                            existing_files.add(line.strip()[4:].strip())
                    insert_pos = target_idx + 1
                    for i in range(target_idx + 1, len(target_section_lines)):
                        if target_section_lines[i].strip().startswith('## '):
                            insert_pos = i
                            break
                    else:
                        insert_pos = len(target_section_lines)
                    new_entries = []
                    for fname in moved_files:
                        if fname not in existing_files:
                            new_entries.append(f'### {fname}')
                    for j, entry in enumerate(new_entries):
                        target_section_lines.insert(insert_pos + j, entry)
                    wiki_text = '\n'.join(target_section_lines)

                wiki_path.write_text(wiki_text, encoding='utf-8')

                for md_file in workspace_path.rglob('*.md'):
                    if md_file.name.startswith('.') or md_file.name.lower() in ('wiki.md', 'tags.md'):
                        continue
                    try:
                        text = md_file.read_text(encoding='utf-8')
                        fm, body = self._parse_frontmatter(text)
                        if fm and isinstance(fm.get('topics'), list):
                            if source in fm['topics']:
                                fm['topics'] = [target if t == source else t for t in fm['topics']]
                                import yaml
                                new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
                                new_content = '---\n' + new_fm + '\n---\n' + body.lstrip('\n')
                                md_file.write_text(new_content, encoding='utf-8')
                    except Exception:
                        continue

            else:
                return {"success": False, "message": "未知的建议类型"}

            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}
