"""WIKI.md 底层存储层门面 — 路径解析、标题解析、编号、综述开关、CRUD、去重、文件夹同步。

本模块是 WIKI.md 唯一的对外入口；实现拆在 ``utils/wiki/{parse,crud,sync}.py``。
生产写入统一走 sidecar/wiki_utils.py 门面。
"""

from __future__ import annotations

from utils.wiki.crud import (
    _deduplicate_files_in_wiki,
    _merge_duplicate_topics_in_wiki,
    _remove_topic_from_wiki,
    add_file_to_wiki_topic,
    create_topic,
    delete_topic,
    remove_file_from_wiki_topic,
    rename_topic,
    rename_wiki_topic,
)
from utils.wiki.parse import (
    WikiTopic,
    _get_wiki_path,
    _renumber_wiki_files,
    collect_survey_off_topics,
    parse_wiki_headings,
    parse_wiki_structure,
)
from utils.wiki.sync import (
    TAGS_END,
    TAGS_START,
    _is_hidden_path,
    _read_legacy_tag_names,
    _render_tag_section,
    _topic_one_line_summary,
    _write_file_topic_from_folder,
    read_wiki_tag_map,
    sync_wiki_with_files,
    topic_from_notes_path,
    write_wiki_tag_map,
)

__all__ = [
    "TAGS_END",
    "TAGS_START",
    "WikiTopic",
    "_deduplicate_files_in_wiki",
    "_get_wiki_path",
    "_is_hidden_path",
    "_merge_duplicate_topics_in_wiki",
    "_read_legacy_tag_names",
    "_remove_topic_from_wiki",
    "_render_tag_section",
    "_renumber_wiki_files",
    "_topic_one_line_summary",
    "_write_file_topic_from_folder",
    "add_file_to_wiki_topic",
    "collect_survey_off_topics",
    "create_topic",
    "delete_topic",
    "parse_wiki_headings",
    "parse_wiki_structure",
    "read_wiki_tag_map",
    "remove_file_from_wiki_topic",
    "rename_topic",
    "rename_wiki_topic",
    "sync_wiki_with_files",
    "topic_from_notes_path",
    "write_wiki_tag_map",
]


def __getattr__(name: str):
    from utils.wiki import crud, parse, sync

    for mod in (parse, crud, sync):
        if hasattr(mod, name):
            value = getattr(mod, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
