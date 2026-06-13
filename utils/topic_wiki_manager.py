"""Thin re-export layer — all implementations live in wiki_crud and wiki_sync."""

from utils.wiki_crud import (  # noqa: F401
    _remove_topic_from_wiki,
    add_file_to_wiki_topic,
    create_topic,
    delete_topic,
    remove_file_from_wiki_topic,
    rename_topic,
    rename_wiki_topic,
)
from utils.wiki_sync import (  # noqa: F401
    _is_hidden_path,
    _topic_one_line_summary,
    _write_file_topic_from_folder,
    sync_wiki_with_files,
    topic_from_notes_path,
)
