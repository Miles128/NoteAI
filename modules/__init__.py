"""modules 包：文件转换 / 预览 / 笔记整合 / 主题提取 / 网页下载。

启动性能优化：本包不再自动导入子模块（此前任何 ``modules.*`` 导入都会触发
全部 5 个子模块及其重依赖（requests/bs4/readability 等）加载，拖慢 sidecar
启动）。改为惰性 ``__getattr__``，仅在真正访问对应类时加载。
"""

from __future__ import annotations

from typing import Any

__all__ = ["WebDownloader", "FileConverterManager", "NoteIntegration", "TopicExtractor", "FilePreviewer"]


def __getattr__(name: str) -> Any:
    if name == "WebDownloader":
        from .web_downloader import WebDownloader

        return WebDownloader
    if name == "FileConverterManager":
        from .file_converter import FileConverterManager

        return FileConverterManager
    if name == "FilePreviewer":
        from .file_preview import FilePreviewer

        return FilePreviewer
    if name == "NoteIntegration":
        from .note_integration import NoteIntegration

        return NoteIntegration
    if name == "TopicExtractor":
        from .topic_extractor import TopicExtractor

        return TopicExtractor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
