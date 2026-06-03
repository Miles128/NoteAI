import json
import re
from pathlib import Path

import yaml

from config import config
from config.constants import TOPIC_SEP
from sidecar.handlers.base import BaseHandler
from sidecar.wiki_utils import (
    ensure_wiki_exists,
    read_wiki_text,
    resolve_wiki_path,
    write_wiki_text,
)
from utils.logger import logger


class IntelTopicHandler(BaseHandler):
    def _ai_topic_analyze(self, params):
        from prompts.ai_topic_consolidate import AI_TOPIC_ANALYZE_PROMPT
        from utils.llm_utils import APIConfigError, call_llm_raw, check_api_config

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
                logger.warning(f"[intel_topic] reading file for topic analysis: {e}\n")
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
        from prompts.topic_survey import TOPIC_SURVEY_PROMPT
        from utils.llm_utils import APIConfigError, check_api_config

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
                if fm and isinstance(fm.get('topics'), list) and topic_name in fm['topics']:
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

            # 方案四：保存到 Abstract/主题名.md（一级主题）或 Abstract/父主题/子主题.md（二级主题）
            abstract_folder = workspace_path / config.ABSTRACT_FOLDER
            abstract_folder.mkdir(parents=True, exist_ok=True)

            if TOPIC_SEP in topic_name:
                # 多级主题
                parts = [p.strip() for p in topic_name.split(TOPIC_SEP) if p.strip()]
                parent_name = parts[0]
                child_name = parts[-1]
                parent_folder = abstract_folder / parent_name
                parent_folder.mkdir(exist_ok=True)
                survey_path = parent_folder / f"{child_name}.md"
            else:
                # 一级主题
                survey_path = abstract_folder / f"{topic_name}.md"
            try:
                survey_path.resolve().relative_to(workspace_path.resolve())
            except ValueError:
                return {"success": False, "message": "主题名称路径非法"}
            fm = {"topic": topic_name, "type": "survey", "tags": [topic_name]}
            fm_str = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
            survey_with_fm = f"---\n{fm_str}\n---\n\n{full_text.strip()}"
            survey_path.write_text(survey_with_fm, encoding='utf-8')
            survey_file = str(survey_path.relative_to(workspace_path))

            self._send_response({
                "id": "event",
                "result": {
                    "type": "survey_done",
                    "topic": topic_name,
                    "success": True,
                    "file_path": survey_file,
                }
            })
            return {"success": True, "message": "综述撰写完成", "file_path": survey_file}
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

        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        suggestion = params.get("suggestion", {})
        stype = suggestion.get("type", "")

        workspace_path = Path(workspace)
        wiki_path = resolve_wiki_path(workspace)

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
        from utils.topic_assigner import move_file_to_notes_topic_folder, write_topic_to_file
        from utils.topic_wiki_manager import add_file_to_wiki_topic, create_topic

        topic_name = suggestion.get("topic", "").strip()
        files = suggestion.get("files", [])
        if not topic_name:
            return {"success": False, "message": "主题名不能为空"}

        create_topic(topic_name)

        for fname in files:
            fn = fname.strip()
            if not fn:
                continue
            for md_file in workspace_path.rglob("*.md"):
                if md_file.is_file() and md_file.name == fn:
                    write_topic_to_file(str(md_file), topic_name)
                    move_file_to_notes_topic_folder(str(md_file), topic_name)
                    add_file_to_wiki_topic(str(md_file), topic_name, Path(fn).stem)

        from sidecar.cascade import append_changelog, collect_topic_notes, ensure_topic_folder, generate_new_survey
        ensure_topic_folder(topic_name)
        notes = collect_topic_notes(topic_name)
        if notes:
            generate_new_survey(topic_name, notes)
            append_changelog(f"AI创建主题并生成综述: {topic_name}")
        return None

    def _apply_change_topic(self, suggestion, workspace_path, wiki_path):
        from utils.topic_assigner import move_file_to_notes_topic_folder, write_topic_to_file
        from utils.topic_wiki_manager import add_file_to_wiki_topic, remove_file_from_wiki_topic

        fname = suggestion.get("file", "").strip()
        new_topic = suggestion.get("suggested_topic", "").strip()
        old_topic = suggestion.get("current_topic", "").strip()
        if not fname or not new_topic:
            return {"success": False, "message": "文件名或主题名不能为空"}

        if old_topic:
            for md_file in workspace_path.rglob("*.md"):
                if md_file.is_file() and md_file.name == fname:
                    remove_file_from_wiki_topic(str(md_file))
                    break

        for md_file in workspace_path.rglob("*.md"):
            if md_file.is_file() and md_file.name == fname:
                write_topic_to_file(str(md_file), new_topic)
                move_file_to_notes_topic_folder(str(md_file), new_topic)
                add_file_to_wiki_topic(str(md_file), new_topic, Path(fname).stem)
                break

        from sidecar.cascade import (
            append_changelog,
            collect_topic_notes,
            ensure_topic_folder,
            generate_new_survey,
            get_survey_path,
            update_existing_survey,
        )
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
        return None

    def _apply_assign_topic(self, suggestion, workspace_path, wiki_path):
        from utils.topic_assigner import move_file_to_notes_topic_folder, write_topic_to_file
        from utils.topic_wiki_manager import add_file_to_wiki_topic

        fname = suggestion.get("file", "").strip()
        topic_name = suggestion.get("topic", "").strip()
        if not fname or not topic_name:
            return {"success": False, "message": "文件名或主题名不能为空"}

        for md_file in workspace_path.rglob("*.md"):
            if md_file.is_file() and md_file.name == fname:
                write_topic_to_file(str(md_file), topic_name)
                move_file_to_notes_topic_folder(str(md_file), topic_name)
                add_file_to_wiki_topic(str(md_file), topic_name, Path(fname).stem)
                break

        from sidecar.cascade import (
            append_changelog,
            collect_topic_notes,
            ensure_topic_folder,
            generate_new_survey,
            get_survey_path,
            update_existing_survey,
        )
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
        return None

    def _apply_merge_topic(self, suggestion, workspace_path, wiki_path):
        from utils.topic_assigner import move_file_to_notes_topic_folder, write_topic_to_file
        from utils.topic_wiki_manager import add_file_to_wiki_topic, remove_file_from_wiki_topic

        source = suggestion.get("source_topic", "").strip()
        target = suggestion.get("target_topic", "").strip()
        if not source or not target:
            return {"success": False, "message": "主题名不能为空"}

        source_files = []
        for md_file in workspace_path.rglob("*.md"):
            if md_file.name.startswith(".") or "wiki" in md_file.parts:
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
                fm, body = self._parse_frontmatter(text)
                if fm and isinstance(fm.get("topics"), list) and source in fm["topics"]:
                    source_files.append((md_file, fm, body))
            except Exception:
                continue

        for md_file, fm, body in source_files:
            fm["topics"] = [target if t == source else t for t in fm["topics"]]
            new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False).strip()
            new_content = "---\n" + new_fm + "\n---\n" + body.lstrip("\n")
            md_file.write_text(new_content, encoding="utf-8")
            remove_file_from_wiki_topic(str(md_file))
            move_file_to_notes_topic_folder(str(md_file), target)
            add_file_to_wiki_topic(str(md_file), target, md_file.stem)

        return None

    def register_routes(self, router):
        router.register("ai_topic_analyze", self._ai_topic_analyze)
        router.register("ai_topic_survey", self._ai_topic_survey, async_mode=True)
        router.register("apply_topic_suggestion", self._apply_topic_suggestion)
