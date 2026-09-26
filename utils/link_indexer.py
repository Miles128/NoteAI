"""双向链接索引引擎（门面）。

保存触发的发现只产生真实引用（正文提及 / 对方摘要提及 / 共享实体概念）。

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
    discover_cross_refs_for_file,
    suggest_links_for_file,
)
from utils.links.persist import (
    cleanup_stale_links,
    load_links,
    save_links,
)

__all__ = [
    "cleanup_stale_links",
    "confirm_all_links",
    "confirm_link",
    "discover_cross_refs_for_file",
    "get_backlinks",
    "load_links",
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
