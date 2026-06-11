"""Thin re-export layer — all implementations live in wiki_crud and wiki_sync."""

from utils.wiki_crud import (  # noqa: F401
    add_file_to_wiki_topic,
    rename_wiki_topic,
    _remove_topic_from_wiki,
    remove_file_from_wiki_topic,
    create_topic,
    delete_topic,
    rename_topic,
)

from utils.wiki_sync import (  # noqa: F401
    _write_file_topic_from_folder,
    _is_hidden_path,
    topic_from_notes_path,
    _topic_one_line_summary,
    sync_wiki_with_files,
)
