import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from utils.topic_manager import TopicManager


class TestFullWorkflow:
    """端到端工作流测试"""

    def test_create_and_build_tree(self, tmp_path, monkeypatch):
        """创建文件结构 → 构建主题树 → 验证层级"""
        from config import config

        # 设置临时工作区
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr(config, "workspace_path", str(workspace))

        # 创建一级 + 二级 + 三级文件夹结构
        notes = workspace / "Notes"
        l1 = notes / "AI应用开发教程"
        l2 = l1 / "Agent 架构设计"
        l3 = l2 / "MCP vs CLI 对比"
        l3.mkdir(parents=True)

        # 写入测试文件
        (l3 / "test.md").write_text("# Test\\n\\nContent", encoding="utf-8")
        (l1 / "overview.md").write_text("# Overview", encoding="utf-8")

        # 模拟构建树
        tree_entries = [
            {"name": "AI应用开发教程", "level": 1, "parent": None},
            {"name": "Agent 架构设计", "level": 2, "parent": "AI应用开发教程"},
            {"name": "MCP vs CLI 对比", "level": 3, "parent": "Agent 架构设计"},
        ]
        tree = TopicManager.build_topic_tree(tree_entries)

        assert len(tree) == 1
        l1_node = tree[0]
        assert l1_node["name"] == "AI应用开发教程"
        assert l1_node["level"] == 1
        assert len(l1_node["children"]) == 1

        l2_node = l1_node["children"][0]
        assert l2_node["name"] == "Agent 架构设计"
        assert l2_node["level"] == 2

        assert len(l2_node["children"]) == 1
        l3_node = l2_node["children"][0]
        assert l3_node["name"] == "MCP vs CLI 对比"
        assert l3_node["level"] == 3

    def test_tree_to_json_format(self):
        """验证前端 JSON 输出格式"""
        entries = [
            {"name": "AI产品经理之路", "level": 1, "parent": None},
            {"name": "需求分析", "level": 2, "parent": "AI产品经理之路"},
        ]
        tree = TopicManager.build_topic_tree(entries)
        json_tree = TopicManager.tree_to_json(tree)

        assert isinstance(json_tree, list)
        assert json_tree[0]["name"] == "AI产品经理之路"
        assert json_tree[0]["level"] == 1
        assert json_tree[0]["parent"] is None
        assert isinstance(json_tree[0]["children"], list)
        assert json_tree[0]["children"][0]["name"] == "需求分析"
        assert json_tree[0]["children"][0]["parent"] == "AI产品经理之路"
        # 必须有这些字段
        for key in ("has_abstract", "abstract_file", "file_count"):
            assert key in json_tree[0]


class TestDeleteProtection:
    """删除保护集成测试"""

    def test_delete_l1_blocked_by_l2(self):
        tree = [
            {
                "name": "AI使用技巧和信息",
                "level": 1,
                "children": [
                    {"name": "工具链", "level": 2, "children": []},
                    {"name": "最佳实践", "level": 2, "children": []},
                ],
            }
        ]
        can, reason = TopicManager.can_delete_topic("AI使用技巧和信息", 1, tree)
        assert can is False
        assert "工具链" in reason
        assert "最佳实践" in reason

    def test_delete_l1_allowed_when_no_children(self):
        tree = [{"name": "AI使用技巧和信息", "level": 1, "children": []}]
        can, _ = TopicManager.can_delete_topic("AI使用技巧和信息", 1, tree)
        assert can is True

    def test_delete_l2_warns_cascade(self):
        tree = [
            {
                "name": "AI应用开发教程",
                "level": 1,
                "children": [
                    {
                        "name": "Agent 架构",
                        "level": 2,
                        "children": [
                            {"name": "MCP", "level": 3, "children": []},
                        ],
                    }
                ],
            }
        ]
        can, reason = TopicManager.can_delete_topic("Agent 架构", 2, tree)
        assert can is True  # 二级可以删
        assert "MCP" in reason  # 但会警告级联


class TestAbstractMutualExclusion:
    """综述互斥集成测试"""

    def test_mutual_exclusion_l1_vs_l2(self):
        tree = [
            {
                "name": "AI产品经理之路",
                "level": 1,
                "has_abstract": False,  # 一级没综述
                "children": [
                    {"name": "需求分析", "level": 2, "has_abstract": True, "children": []},  # 二级有
                    {"name": "竞品分析", "level": 2, "has_abstract": False, "children": []},
                ],
            }
        ]
        # 一级不能再设综述
        can, reason = TopicManager.can_generate_abstract("AI产品经理之路", tree)
        assert can is False

        # 竞品分析可以设综述（其他二级有也不影响）
        can2, _ = TopicManager.can_generate_abstract("竞品分析", tree)
        assert can2 is True


class TestFolderLevelDetermination:
    """文件夹层级判定"""

    @pytest.mark.parametrize(
        "parent,expected",
        [
            ("Notes/AI产品经理之路", 2),
            ("Notes/AI产品经理之路/需求分析", 3),
            ("Notes/AI产品经理之路/需求分析/细节", -1),
            ("Notes", 1),
        ],
    )
    def test_level_determination(self, tmp_path, parent, expected):
        p = tmp_path / parent
        p.mkdir(parents=True)
        level = TopicManager.determine_folder_level(str(p), str(tmp_path))
        assert level == expected
