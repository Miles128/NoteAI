"""主题归属判定：单篇笔记是否属于指定主题的唯一实现。

判定标准（任一命中即归属）：
1. frontmatter topic 与目标主题相同，或为其前缀子主题；
2. frontmatter topics 列表包含目标主题；
3. 笔记在 Notes/ 下的相对路径前缀与主题层级逐级匹配。

cascade.collect_topic_notes、topics_handler 过期检测、wiki_utils 综述概览
三处共用本模块，禁止再复制判定逻辑。
"""

from __future__ import annotations

from config.constants import TOPIC_SEP


def split_topic_parts(topic: str) -> list[str]:
    """主题按层级分隔符拆成非空层级列表。"""
    return [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]


def note_belongs_to_topic(
    topic: str,
    file_topic: str,
    file_topics: list,
    notes_rel_parts: tuple[str, ...] | list[str] | None,
    topic_parts: list[str] | None = None,
) -> bool:
    """判定一篇笔记是否归属 topic。

    Args:
        topic: 目标主题（可含 TOPIC_SEP 层级）。
        file_topic: 笔记 frontmatter 的 topic（调用方保证为 str）。
        file_topics: 笔记 frontmatter 的 topics 列表（非 list 时传 []）。
        notes_rel_parts: 笔记相对 Notes/ 目录的路径 parts；不在 Notes/ 下传空。
        topic_parts: 可选，预先算好的 split_topic_parts(topic)，批量判定复用。
    """
    if topic_parts is None:
        topic_parts = split_topic_parts(topic)
    if file_topic and (
        file_topic == topic
        or topic_parts
        and file_topic.startswith(topic + TOPIC_SEP)
        or len(topic_parts) == 1
        and (file_topic == topic_parts[0] or file_topic.startswith(topic_parts[0] + TOPIC_SEP))
    ):
        return True
    if isinstance(file_topics, list) and topic in file_topics:
        return True
    rel_parts = tuple(notes_rel_parts or ())
    if topic_parts and rel_parts and rel_parts[0] == topic_parts[0]:
        if len(topic_parts) == 1:
            return True
        if len(rel_parts) >= 2 and rel_parts[1] == topic_parts[1]:
            if len(topic_parts) == 2 or len(rel_parts) >= 3 and rel_parts[2] == topic_parts[2]:
                return True
    return False
