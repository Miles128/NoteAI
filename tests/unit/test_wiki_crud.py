"""单元测试：utils/wiki_crud.py 的 WIKI.md CRUD 全链路。

使用临时工作区 fixture 构造最小 WIKI.md 结构，覆盖段落创建/读取/
更新/删除的 happy path 与目标不存在等边界。
"""

from pathlib import Path

import pytest

from config import config
from utils.wiki_crud import (
    _remove_topic_from_wiki,
    add_file_to_wiki_topic,
    create_topic,
    delete_topic,
    remove_file_from_wiki_topic,
    rename_topic,
    rename_wiki_topic,
)

WIKI_TEMPLATE = """# WIKI

生成时间: 2026-08-06 10:00
主题数量: 2

## 目录

## AI基础

1. **深度学习入门**
2. **神经网络概览**

## 编程工具

1. **Python技巧**
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "ws"
    (root / "wiki").mkdir(parents=True)
    (root / "Notes").mkdir()
    (root / "wiki" / "WIKI.md").write_text(WIKI_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(config, "workspace_path", str(root))
    return root


def read_wiki(workspace: Path) -> str:
    return (workspace / "wiki" / "WIKI.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# add_file_to_wiki_topic
# ---------------------------------------------------------------------------


def test_add_file_to_existing_topic_appends_and_renumbers(workspace: Path):
    assert add_file_to_wiki_topic("Notes/AI基础/新笔记.md", "AI基础") is True

    wiki = read_wiki(workspace)
    assert "3. **新笔记**" in wiki
    # 顺序：新条目追加在该主题原有条目之后
    assert wiki.index("**深度学习入门**") < wiki.index("**神经网络概览**") < wiki.index("**新笔记**")
    # 不影响其他主题
    assert "1. **Python技巧**" in wiki


def test_add_file_with_explicit_title_uses_title(workspace: Path):
    assert add_file_to_wiki_topic("Notes/任意路径.md", "编程工具", file_title="自定义标题") is True
    wiki = read_wiki(workspace)
    assert "2. **自定义标题**" in wiki
    assert "任意路径" not in wiki


def test_add_duplicate_file_is_noop(workspace: Path):
    before = read_wiki(workspace)
    assert add_file_to_wiki_topic("Notes/AI基础/深度学习入门.md", "AI基础") is True
    assert read_wiki(workspace) == before
    assert before.count("**深度学习入门**") == 1


def test_add_file_creates_new_topic_section(workspace: Path):
    assert add_file_to_wiki_topic("Notes/笔记A.md", "新主题") is True
    wiki = read_wiki(workspace)
    assert "## 新主题" in wiki
    assert "1. **笔记A**" in wiki


def test_add_file_creates_nested_topic_with_missing_parent(workspace: Path):
    assert add_file_to_wiki_topic("Notes/子笔记.md", "父级 > 子级") is True
    wiki = read_wiki(workspace)
    assert "## 父级" in wiki
    assert "### 子级" in wiki
    assert "1. **子笔记**" in wiki


def test_add_file_normalizes_slash_separator(workspace: Path):
    assert add_file_to_wiki_topic("Notes/斜杠笔记.md", "A组/B组") is True
    wiki = read_wiki(workspace)
    assert "## A组" in wiki
    assert "### B组" in wiki
    assert "A组/B组" not in wiki


def test_add_file_without_workspace_returns_false(monkeypatch):
    monkeypatch.setattr(config, "workspace_path", "")
    assert add_file_to_wiki_topic("Notes/x.md", "主题") is False


# ---------------------------------------------------------------------------
# rename_wiki_topic
# ---------------------------------------------------------------------------


def test_rename_wiki_topic_updates_heading_and_moves_dir(workspace: Path):
    notes_topic = workspace / "Notes" / "AI基础"
    notes_topic.mkdir()
    (notes_topic / "深度学习入门.md").write_text("内容", encoding="utf-8")

    ok, titles = rename_wiki_topic("AI基础", "机器学习")
    assert ok is True
    assert titles == ["深度学习入门", "神经网络概览"]

    wiki = read_wiki(workspace)
    assert "## 机器学习" in wiki
    assert "## AI基础" not in wiki
    assert "1. **深度学习入门**" in wiki
    assert (workspace / "Notes" / "机器学习").is_dir()
    assert not notes_topic.exists()


def test_rename_wiki_topic_missing_target_reports_failure_and_noop(workspace: Path):
    # 正确行为：目标主题不存在时返回失败信号，且内容无任何变化
    before = read_wiki(workspace)
    ok, titles = rename_wiki_topic("不存在的主题", "随便")
    assert ok is False
    assert titles == []
    assert read_wiki(workspace) == before


# ---------------------------------------------------------------------------
# _remove_topic_from_wiki
# ---------------------------------------------------------------------------


def test_remove_topic_deletes_section_and_returns_titles(workspace: Path):
    ok, removed = _remove_topic_from_wiki("AI基础")
    assert ok is True
    assert removed == ["深度学习入门", "神经网络概览"]

    wiki = read_wiki(workspace)
    assert "## AI基础" not in wiki
    assert "深度学习入门" not in wiki
    # 其他主题保持完整
    assert "## 编程工具" in wiki
    assert "1. **Python技巧**" in wiki


def test_remove_missing_topic_is_noop(workspace: Path):
    before = read_wiki(workspace)
    ok, removed = _remove_topic_from_wiki("幽灵主题")
    assert ok is True
    assert removed == []
    assert read_wiki(workspace) == before


# ---------------------------------------------------------------------------
# remove_file_from_wiki_topic
# ---------------------------------------------------------------------------


def test_remove_file_deletes_item_and_renumbers(workspace: Path):
    ok, old_topic = remove_file_from_wiki_topic("Notes/AI基础/深度学习入门.md")
    assert ok is True
    assert old_topic == "AI基础"

    wiki = read_wiki(workspace)
    assert "深度学习入门" not in wiki
    # 剩余条目重新编号为 1
    assert "1. **神经网络概览**" in wiki


def test_remove_missing_file_keeps_content(workspace: Path):
    before = read_wiki(workspace)
    ok, old_topic = remove_file_from_wiki_topic("Notes/AI基础/不存在的文件.md")
    assert ok is True
    assert old_topic is None
    assert read_wiki(workspace) == before


# ---------------------------------------------------------------------------
# create_topic
# ---------------------------------------------------------------------------


def test_create_topic_adds_heading_and_notes_dir(workspace: Path):
    result = create_topic("数学")
    assert result["success"] is True
    assert "数学" in result["message"]
    assert "## 数学" in read_wiki(workspace)
    assert (workspace / "Notes" / "数学").is_dir()


def test_create_topic_rejects_duplicate_case_insensitive(workspace: Path):
    before = read_wiki(workspace)
    result = create_topic("ai基础")
    assert result["success"] is False
    assert "已存在" in result["message"]
    assert read_wiki(workspace) == before


def test_create_topic_rejects_empty_name(workspace: Path):
    for name in ("", "   "):
        result = create_topic(name)
        assert result["success"] is False
        assert result["message"] == "主题名不能为空"


def test_create_nested_topic_creates_parent_chain(workspace: Path):
    result = create_topic("技术 > 前端")
    assert result["success"] is True

    wiki = read_wiki(workspace)
    assert "## 技术" in wiki
    assert "### 前端" in wiki
    assert wiki.index("## 技术") < wiki.index("### 前端")
    assert (workspace / "Notes" / "技术" / "前端").is_dir()


def test_create_topic_without_workspace_fails(monkeypatch):
    monkeypatch.setattr(config, "workspace_path", "")
    assert create_topic("主题") == {"success": False, "message": "未设置工作区"}


# ---------------------------------------------------------------------------
# delete_topic
# ---------------------------------------------------------------------------


def _wiki_with_topic(extra_section: str) -> str:
    return WIKI_TEMPLATE + extra_section


def test_delete_topic_moves_files_and_removes_wiki_section(workspace: Path, monkeypatch):
    topic_dir = workspace / "Notes" / "待删主题"
    topic_dir.mkdir()
    (topic_dir / "甲文件.md").write_text("# 甲\n", encoding="utf-8")
    (topic_dir / "乙文件.md").write_text("# 乙\n", encoding="utf-8")
    (workspace / "wiki" / "WIKI.md").write_text(
        _wiki_with_topic("\n## 待删主题\n\n1. **甲文件**\n2. **乙文件**\n"), encoding="utf-8"
    )
    monkeypatch.setattr(
        "utils.topic_assigner.auto_assign_topic_for_file", lambda path: {"status": "pending"}
    )

    result = delete_topic("待删主题")

    assert result["success"] is True
    assert result["moved"] == 2
    assert result["pending"] == 2
    assert result["reassigned"] == 0
    assert not topic_dir.exists()
    assert (workspace / "Notes" / "甲文件.md").is_file()
    assert (workspace / "Notes" / "乙文件.md").is_file()

    wiki = read_wiki(workspace)
    assert "## 待删主题" not in wiki
    assert "## AI基础" in wiki


def test_delete_topic_counts_reassigned_files(workspace: Path, monkeypatch):
    topic_dir = workspace / "Notes" / "重分配主题"
    topic_dir.mkdir()
    (topic_dir / "文件.md").write_text("# 内容\n", encoding="utf-8")
    (workspace / "wiki" / "WIKI.md").write_text(
        _wiki_with_topic("\n## 重分配主题\n\n1. **文件**\n"), encoding="utf-8"
    )
    monkeypatch.setattr(
        "utils.topic_assigner.auto_assign_topic_for_file", lambda path: {"status": "auto_assigned"}
    )

    result = delete_topic("重分配主题")
    assert result["moved"] == 1
    assert result["reassigned"] == 1
    assert result["pending"] == 0


def test_delete_missing_topic_is_graceful(workspace: Path, monkeypatch):
    monkeypatch.setattr(
        "utils.topic_assigner.auto_assign_topic_for_file", lambda path: {"status": "pending"}
    )
    before = read_wiki(workspace)

    result = delete_topic("不存在主题")
    assert result["success"] is True
    assert result["moved"] == 0
    assert result["pending"] == 0
    assert read_wiki(workspace) == before


# ---------------------------------------------------------------------------
# rename_topic（含合并分支）
# ---------------------------------------------------------------------------


def test_rename_topic_same_name_is_noop(workspace: Path):
    result = rename_topic("AI基础", "AI基础")
    assert result == {"success": True, "message": "主题名相同，无需修改", "updated": 0, "merged": False}


def test_rename_topic_empty_name_fails(workspace: Path):
    result = rename_topic("", "新名")
    assert result["success"] is False
    assert result["message"] == "主题名不能为空"


def test_rename_topic_simple_path_updates_files_and_dir(workspace: Path, monkeypatch):
    # WIKI.md 中先登记旧主题及其文件
    (workspace / "wiki" / "WIKI.md").write_text(
        _wiki_with_topic("\n## 旧主题\n\n1. **文件A**\n"), encoding="utf-8"
    )
    old_dir = workspace / "Notes" / "旧主题"
    old_dir.mkdir()
    (old_dir / "文件A.md").write_text("---\n---\n内容\n", encoding="utf-8")

    written: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "utils.topic_assigner.write_topic_to_file", lambda path, topic: written.append((path, topic))
    )

    result = rename_topic("旧主题", "新主题")
    assert result["success"] is True
    assert result["merged"] is False

    wiki = read_wiki(workspace)
    assert "## 新主题" in wiki
    assert "## 旧主题" not in wiki
    assert (workspace / "Notes" / "新主题" / "文件A.md").is_file()
    assert not old_dir.exists()

    # 正确行为：目录改名后按新目录扫描，write_topic_to_file 被调用且计数正确
    assert result["updated"] == 1
    assert written == [(str(workspace / "Notes" / "新主题" / "文件A.md"), "新主题")]


def test_rename_topic_updates_file_frontmatter(workspace: Path):
    # 端到端验证：不 mock write_topic_to_file，frontmatter 中的 topic 应被更新
    (workspace / "wiki" / "WIKI.md").write_text(
        _wiki_with_topic("\n## 旧主题\n\n1. **文件A**\n"), encoding="utf-8"
    )
    old_dir = workspace / "Notes" / "旧主题"
    old_dir.mkdir()
    (old_dir / "文件A.md").write_text("---\ntopic: 旧主题\n---\n内容\n", encoding="utf-8")

    result = rename_topic("旧主题", "新主题")
    assert result["success"] is True
    assert result["updated"] == 1

    moved = workspace / "Notes" / "新主题" / "文件A.md"
    assert moved.is_file()
    text = moved.read_text(encoding="utf-8")
    assert "topic: 新主题" in text
    assert "旧主题" not in text


def test_rename_topic_into_existing_topic_merges(workspace: Path, monkeypatch):
    (workspace / "wiki" / "WIKI.md").write_text(
        _wiki_with_topic("\n## 甲\n\n1. **甲文件**\n\n## 乙\n\n1. **乙文件**\n"), encoding="utf-8"
    )
    jia_dir = workspace / "Notes" / "甲"
    jia_dir.mkdir()
    (jia_dir / "甲文件.md").write_text("---\n---\n内容\n", encoding="utf-8")
    (workspace / "Notes" / "乙").mkdir()

    monkeypatch.setattr("utils.topic_assigner.write_topic_to_file", lambda path, topic: None)

    result = rename_topic("甲", "乙")
    assert result["success"] is True
    assert result["merged"] is True
    assert result["updated"] == 1

    wiki = read_wiki(workspace)
    assert "## 甲" not in wiki
    yi_section = wiki.split("## 乙", 1)[1]
    assert "**甲文件**" in yi_section
    assert "**乙文件**" in yi_section

    assert not jia_dir.exists()
    assert (workspace / "Notes" / "乙" / "甲文件.md").is_file()


def test_rename_topic_missing_old_and_new_exists_fails(workspace: Path, monkeypatch):
    monkeypatch.setattr("utils.topic_assigner.write_topic_to_file", lambda path, topic: None)
    result = rename_topic("幽灵主题", "AI基础")
    assert result["success"] is False
    assert "不存在" in result["message"]
    assert result["merged"] is False
