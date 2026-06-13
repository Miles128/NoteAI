import sys
from pathlib import Path

# 确保项目路径在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from utils.topic_manager import (
    LEVEL1_TOPICS,
    MAX_LEVEL,
    TopicManager,
)


class TestParseTopicHierarchy:
    """测试 YAML frontmatter 解析"""

    def test_single_level1(self):
        fm = {"topic": ["普通人的AI指南"]}
        result = TopicManager.parse_topic_hierarchy(fm)
        assert len(result) == 1
        assert result[0] == {"name": "普通人的AI指南", "level": 1, "parent": None}

    def test_level1_and_level2(self):
        fm = {"topic": ["普通人的AI指南", {"AI Agent 核心架构设计": []}]}
        result = TopicManager.parse_topic_hierarchy(fm)
        assert len(result) == 2
        assert result[0] == {"name": "普通人的AI指南", "level": 1, "parent": None}
        assert result[1] == {"name": "AI Agent 核心架构设计", "level": 2, "parent": "普通人的AI指南"}

    def test_full_three_levels(self):
        fm = {"topic": ["AI应用开发教程", {"Agent 架构设计": [{"MCP vs CLI 对比": []}]}]}
        result = TopicManager.parse_topic_hierarchy(fm)
        assert len(result) == 3
        assert result[0]["level"] == 1
        assert result[1]["level"] == 2
        assert result[2]["level"] == 3
        assert result[2]["parent"] == "Agent 架构设计"

    def test_empty_topic(self):
        result = TopicManager.parse_topic_hierarchy({})
        assert result == []

    def test_any_level1_accepted(self):
        fm = {"topic": ["任意标题"]}
        result = TopicManager.parse_topic_hierarchy(fm)
        assert len(result) == 1
        assert result[0]["name"] == "任意标题"
        assert result[0]["level"] == 1


class TestBuildTopicTree:
    """测试主题树构建"""

    def test_flat_to_nested(self):
        entries = [
            {"name": "普通人的AI指南", "level": 1, "parent": None},
            {"name": "AI Agent 核心架构设计", "level": 2, "parent": "普通人的AI指南"},
            {"name": "RAG 知识库", "level": 2, "parent": "普通人的AI指南"},
            {"name": "切片策略", "level": 3, "parent": "RAG 知识库"},
        ]
        tree = TopicManager.build_topic_tree(entries)
        assert len(tree) == 1
        l1 = tree[0]
        assert l1["name"] == "普通人的AI指南"
        assert len(l1["children"]) == 2
        assert l1["children"][0]["name"] in ("AI Agent 核心架构设计", "RAG 知识库")

        # 找 RAG 的三级子题
        rag = next(c for c in l1["children"] if c["name"] == "RAG 知识库")
        assert len(rag["children"]) == 1
        assert rag["children"][0]["name"] == "切片策略"

    def test_empty_entries(self):
        tree = TopicManager.build_topic_tree([])
        assert tree == []


class TestResolveTopicFromPath:
    """测试路径 → 主题解析"""

    def test_three_level_path(self, tmp_path):
        # 创建目录结构
        l1 = tmp_path / "Notes" / "普通人的AI指南"
        l1.mkdir(parents=True)
        l2 = l1 / "AI Agent 核心架构设计"
        l2.mkdir()
        l3 = l2 / "MCP vs CLI 对比"
        l3.mkdir()
        f = l3 / "test.md"
        f.write_text("# Test")

        topics = TopicManager.resolve_topic_from_path(str(f), str(tmp_path))
        assert len(topics) <= 3
        # 至少能识别到一级
        names = [t["name"] for t in topics]
        assert "普通人的AI指南" in names

    def test_outside_workspace(self, tmp_path):
        topics = TopicManager.resolve_topic_from_path("/etc/passwd", str(tmp_path))
        assert topics == []


class TestFolderLevel:
    """测试文件夹层级判定"""

    def test_under_level1(self, tmp_path):
        l1 = tmp_path / "Notes" / "AI使用技巧和信息"
        l1.mkdir(parents=True)
        level = TopicManager.determine_folder_level(str(l1), str(tmp_path))
        assert level == 2  # 在一级文件夹下新建 → 二级

    def test_under_level2(self, tmp_path):
        l2 = tmp_path / "Notes" / "AI应用开发教程" / "Agent 架构设计"
        l2.mkdir(parents=True)
        level = TopicManager.determine_folder_level(str(l2), str(tmp_path))
        assert level == 3  # 在二级文件夹下新建 → 三级

    def test_under_level3(self, tmp_path):
        l3 = tmp_path / "Notes" / "AI使用技巧和信息" / "工具链" / "配置技巧"
        l3.mkdir(parents=True)
        level = TopicManager.determine_folder_level(str(l3), str(tmp_path))
        assert level == -1  # 三级下不再作为标题


class TestCanDeleteTopic:
    """测试删除保护"""

    def test_level1_with_children_cannot_delete(self):
        tree = [
            {
                "name": "AI产品经理之路",
                "level": 1,
                "children": [{"name": "需求分析", "level": 2, "children": []}],
            }
        ]
        can, reason = TopicManager.can_delete_topic("AI产品经理之路", 1, tree)
        assert can is False
        assert "需求分析" in reason

    def test_level1_empty_can_delete(self):
        tree = [{"name": "AI应用开发教程", "level": 1, "children": []}]
        can, reason = TopicManager.can_delete_topic("AI应用开发教程", 1, tree)
        # 注意：预定义一级不能删除是通过外层逻辑控制的
        # 这里只测试删除保护逻辑
        assert can is True

    def test_level2_can_delete(self):
        tree = [
            {
                "name": "AI应用开发教程",
                "level": 1,
                "children": [
                    {
                        "name": "Agent 架构设计",
                        "level": 2,
                        "children": [
                            {"name": "MCP", "level": 3, "children": []},
                            {"name": "Skills", "level": 3, "children": []},
                        ],
                    }
                ],
            }
        ]
        can, reason = TopicManager.can_delete_topic("Agent 架构设计", 2, tree)
        assert can is True
        assert "MCP" in reason  # 警告级联删除

    def test_level3_always_can_delete(self):
        can, reason = TopicManager.can_delete_topic("anything", 3, [])
        assert can is True


class TestAbstractControl:
    """测试综述互斥"""

    def test_level1_ok_when_no_level2_abstract(self):
        tree = [
            {
                "name": "AI产品经理之路",
                "level": 1,
                "has_abstract": False,
                "children": [
                    {"name": "需求分析", "level": 2, "has_abstract": False, "children": []},
                ],
            }
        ]
        can, reason = TopicManager.can_generate_abstract("AI产品经理之路", tree)
        assert can is True

    def test_level1_blocked_when_level2_has_abstract(self):
        tree = [
            {
                "name": "AI产品经理之路",
                "level": 1,
                "has_abstract": False,
                "children": [
                    {"name": "需求分析", "level": 2, "has_abstract": True, "children": []},
                ],
            }
        ]
        can, reason = TopicManager.can_generate_abstract("AI产品经理之路", tree)
        assert can is False

    def test_level2_blocked_when_level1_has_abstract(self):
        tree = [
            {
                "name": "AI应用开发教程",
                "level": 1,
                "has_abstract": True,
                "children": [
                    {"name": "Agent 架构", "level": 2, "has_abstract": False, "children": []},
                ],
            }
        ]
        can, reason = TopicManager.can_generate_abstract("Agent 架构", tree)
        assert can is False

    def test_level3_no_abstract(self):
        can, reason = TopicManager.can_generate_abstract("MCP vs CLI", [], level=3)
        assert can is False
        assert "三级" in reason


class TestLevel1Topics:
    """验证一级标题不再硬编码，由文件系统决定"""

    def test_level1_topics_is_empty(self):
        assert len(LEVEL1_TOPICS) == 0

    def test_max_level_is_three(self):
        assert MAX_LEVEL == 3
