"""工作区笔记统一扫描入口。

所有"遍历 Notes/（或扩展文件夹）收集 Markdown 笔记"的逻辑都应走这里，
避免各模块各自 rglob 造成过滤规则漂移。
"""

from pathlib import Path

from config.constants import NOTES_FOLDER

_SURVEY_SUFFIX = "_综述.md"


def iter_note_files(
    workspace: str | Path,
    folders: list[str] | None = None,
    *,
    include_surveys: bool = False,
    include_hidden: bool = False,
) -> list[Path]:
    """扫描指定文件夹下的 Markdown 笔记。

    Args:
        workspace: 工作区根路径。
        folders: 要扫描的子文件夹列表，默认仅 Notes/。
        include_surveys: 是否包含 *_综述.md（默认排除）。
        include_hidden: 是否包含以 "." 开头的文件（默认排除）。

    Returns:
        笔记文件路径列表（rglob 顺序，未排序）。
    """
    ws = Path(workspace)
    targets = folders if folders else [NOTES_FOLDER]
    out: list[Path] = []
    for folder_name in targets:
        folder = ws / folder_name
        if not folder.exists():
            continue
        for md in folder.rglob("*.md"):
            if not include_hidden and md.name.startswith("."):
                continue
            if not include_surveys and md.name.endswith(_SURVEY_SUFFIX):
                continue
            out.append(md)
    return out
