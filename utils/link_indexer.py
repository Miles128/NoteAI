"""双向链接索引引擎（门面）。

两阶段发现：
1. 本地粗筛：同 topic / 共享 tag / 文件名 token 重叠 → 候选对
2. AI 精判：批处理候选对，LLM 判断是否内容相关

存储：workspace/.links.json

实现拆在 ``utils/links/{persist,discover,actions}.py``。
"""

from __future__ import annotations

from utils.links.actions import (
    confirm_all_links,
    confirm_link,
    get_backlinks,
    reject_link,
)
from utils.links.discover import (
    backfill_semantic_bidirectional,
    discover_cross_refs_for_file,
    discover_links,
    suggest_links_for_file,
)
from utils.links.persist import (
    cleanup_stale_links,
    load_links,
    purge_weak_links,
    save_links,
)

__all__ = [
    "backfill_semantic_bidirectional",
    "cleanup_stale_links",
    "confirm_all_links",
    "confirm_link",
    "discover_cross_refs_for_file",
    "discover_links",
    "get_backlinks",
    "load_links",
    "purge_weak_links",
    "reject_link",
    "save_links",
    "suggest_links_for_file",
]


def __getattr__(name: str):
    from utils.links import actions, discover, persist

    for mod in (persist, discover, actions):
        if hasattr(mod, name):
            value = getattr(mod, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
