import json
import re
import sys
from pathlib import Path

import yaml
from config import config
from sidecar.handlers.base import BaseHandler


class IntelTopicHandler(BaseHandler):
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
            if 'wiki' in md_file.parts:
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
            except Exception as e:
                sys.stderr.write(f"[intel_topic] reading file for topic analysis: {e}\n")
                sys.stderr.flush()
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
            json_match = re.search(r'\{[\s\S]*?\}', result_text)
            if not json_match:
                return {"success": False, "message": "LLM 返回格式异常"}
            json_str = json_match.group()
            try:
                suggestions = json.loads(json_str)
            except json.JSONDecodeError:
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
        from utils.llm_utils import check_api_config, APIConfigError
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
            if 'wiki' in md_file.parts:
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
            from utils.llm_utils import create_llm

            llm = create_llm(temperature=0.3)
            pt = PromptTemplate(template=prompt, input_variables=[])
            chain = pt | llm

            for chunk in chain.stream({}):
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                full_text += token
                on_chunk(token)

            safe_name = "".join(c for c in topic_name if c.isalnum() or c in ('_', '-', '.', ' ') or '\u4e00' <= c <= '\u9fff').strip()
            if not safe_name or '..' in safe_name:
                return {"success": False, "message": "主题名称包含非法字符"}
            survey_filename = f"{safe_name}_综述.md"
            # 保存到 Abstract/主题名/ 子目录，与 cascade.py 保持一致
            from config.settings import ORGANIZED_FOLDER
            survey_dir = workspace_path / ORGANIZED_FOLDER / topic_name
            survey_dir.mkdir(parents=True, exist_ok=True)
            survey_path = survey_dir / survey_filename
            try:
                survey_path.resolve().relative_to(workspace_path.resolve())
            except ValueError:
                return {"success": False, "message": "主题名称路径非法"}
            fm = {"topic": topic_name, "type": "survey", "tags": [topic_name]}
            fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
            survey_with_fm = f"---\n{fm_str}\n---\n\n{full_text.strip()}"
            survey_path.write_text(survey_with_fm, encoding='utf-8')

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
        from utils.topic_assigner import write_topic_to_file, move_file_to_notes_topic_folder

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        suggestion = params.get("suggestion", {})
        stype = suggestion.get("type", "")

        workspace_path = Path(workspace)
        wiki_path = workspace_path / "wiki" / "WIKI.md"
        if not wiki_path.exists():
            wiki_path = workspace_path / "WIKI.md"

        try:
            if stype == "new_topic":
                self._apply_new_topic(suggestion, workspace_path, wiki_path)
            elif stype == "change_topic":
                self._apply_change_topic(suggestion, workspace_path, wiki_path)
            elif stype == "assign_topic":
                self._apply_assign_topic(suggestion, workspace_path, wiki_path)
            elif stype == "merge_topic":
                self._apply_merge_topic(suggestion, workspace_path, wiki_path)
            else:
                return {"success": False, "message": "未知的建议类型"}

            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _apply_new_topic(self, suggestion, workspace_path, wiki_path):
        from utils.topic_assigner import write_topic_to_file, move_file_to_notes_topic_folder

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

        notes_topic_dir = workspace_path / config.NOTES_FOLDER / topic_name
        notes_topic_dir.mkdir(parents=True, exist_ok=True)

        for fname in files:
            fn = fname.strip()
            if not fn:
                continue
            for md_file in workspace_path.rglob("*.md"):
                if md_file.is_file() and md_file.name == fn:
                    write_topic_to_file(str(md_file), topic_name)
                    move_file_to_notes_topic_folder(str(md_file), topic_name)

        from sidecar.cascade import ensure_topic_folder, collect_topic_notes, generate_new_survey, append_changelog
        ensure_topic_folder(topic_name)
        notes = collect_topic_notes(topic_name)
        if notes:
            generate_new_survey(topic_name, notes)
            append_changelog(f"AI创建主题并生成综述: {topic_name}")

    def _apply_change_topic(self, suggestion, workspace_path, wiki_path):
        from utils.topic_assigner import write_topic_to_file, move_file_to_notes_topic_folder

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

        notes_topic_dir = workspace_path / config.NOTES_FOLDER / new_topic
        notes_topic_dir.mkdir(parents=True, exist_ok=True)

        for md_file in workspace_path.rglob("*.md"):
            if md_file.is_file() and md_file.name == fname:
                write_topic_to_file(str(md_file), new_topic)
                move_file_to_notes_topic_folder(str(md_file), new_topic)

        from sidecar.cascade import ensure_topic_folder, collect_topic_notes, update_existing_survey, get_survey_path, generate_new_survey, append_changelog
        ensure_topic_folder(new_topic)
        notes = collect_topic_notes(new_topic)
        if notes:
            survey_path = get_survey_path(new_topic)
            if survey_path and survey_path.exists():
                new_file_notes = [n for n in notes if n["file_name"] == fname]
                if not new_file_notes:
                    new_file_notes = [notes[-1]]
                update_existing_survey(new_topic, new_file_notes)
            else:
                generate_new_survey(new_topic, notes)
            append_changelog(f"AI变更主题并更新综述: {fname} → {new_topic}")

    def _apply_assign_topic(self, suggestion, workspace_path, wiki_path):
        from utils.topic_assigner import write_topic_to_file, move_file_to_notes_topic_folder

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

        notes_topic_dir = workspace_path / config.NOTES_FOLDER / topic_name
        notes_topic_dir.mkdir(parents=True, exist_ok=True)

        for md_file in workspace_path.rglob("*.md"):
            if md_file.is_file() and md_file.name == fname:
                write_topic_to_file(str(md_file), topic_name)
                move_file_to_notes_topic_folder(str(md_file), topic_name)

        from sidecar.cascade import ensure_topic_folder, collect_topic_notes, update_existing_survey, get_survey_path, generate_new_survey, append_changelog
        ensure_topic_folder(topic_name)
        notes = collect_topic_notes(topic_name)
        if notes:
            survey_path = get_survey_path(topic_name)
            if survey_path and survey_path.exists():
                new_file_notes = [n for n in notes if n["file_name"] == fname]
                if not new_file_notes:
                    new_file_notes = [notes[-1]]
                update_existing_survey(topic_name, new_file_notes)
            else:
                generate_new_survey(topic_name, notes)
            append_changelog(f"AI分配主题并更新综述: {fname} → {topic_name}")

    def _apply_merge_topic(self, suggestion, workspace_path, wiki_path):
        from utils.topic_assigner import move_file_to_notes_topic_folder

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

        notes_target_dir = workspace_path / config.NOTES_FOLDER / target
        notes_target_dir.mkdir(parents=True, exist_ok=True)

        for md_file in workspace_path.rglob('*.md'):
            if md_file.name.startswith('.') or 'wiki' in md_file.parts:
                continue
            try:
                text = md_file.read_text(encoding='utf-8')
                fm, body = self._parse_frontmatter(text)
                if fm and isinstance(fm.get('topics'), list):
                    if source in fm['topics']:
                        fm['topics'] = [target if t == source else t for t in fm['topics']]
                        new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
                        new_content = '---\n' + new_fm + '\n---\n' + body.lstrip('\n')
                        md_file.write_text(new_content, encoding='utf-8')
                        move_file_to_notes_topic_folder(str(md_file), target)
            except Exception:
                continue

    def register_routes(self, router):
        router.register("ai_topic_analyze", self._ai_topic_analyze)
        router.register("ai_topic_survey", self._ai_topic_survey, async_mode=True)
        router.register("apply_topic_suggestion", self._apply_topic_suggestion)