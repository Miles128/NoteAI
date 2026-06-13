"""Step 1: TopicManager — 三层主题数据结构与管理

三层标题体系：
  Level 1 (领域):  一级标题，6 个预定义
  Level 2 (方向):  二级标题，分属某一级
  Level 3 (子题):  三级标题，分属某二级，最多三层

YAML frontmatter 标记规则（横杠缩进）:
  topic:
  - 普通人的 AI 学习指南          # 一级（0 缩进）
    - AI Agent 核心架构设计        # 二级（2 空格缩进）
      - MCP vs CLI 对比            # 三级（4 空格缩进）
"""

import logging
from pathlib import Path

from config.constants import TOPIC_SEP

logger = logging.getLogger(__name__)

# ============================================================
# 预定义的 4 个一级标题
# ============================================================
LEVEL1_TOPICS = []

MAX_LEVEL = 3
LEVEL1_ORDER = {}


class TopicManager:
    """三层主题管理器

    职责：
    - 解析 YAML frontmatter 中的 topic 层级
    - 构建嵌套主题树
    - 验证层级关系
    - 管理主题与文件/文件夹的映射
    """

    # ============================================================
    # 解析 frontmatter
    # ============================================================
    @staticmethod
    def parse_topic_hierarchy(frontmatter: dict) -> list[dict]:
        """从 frontmatter 解析三层主题结构

        输入 frontmatter 中 topic 字段的 YAML 结构:
          topic:
          - L1名称
            - L2名称
              - L3名称

        返回:
          [
            {"name": "L1名称", "level": 1, "parent": None},
            {"name": "L2名称", "level": 2, "parent": "L1名称"},
            {"name": "L3名称", "level": 3, "parent": "L2名称"},
          ]
        """
        topics = []
        raw = frontmatter.get("topic", [])
        if not raw:
            return topics

        current_l1 = None
        current_l2 = None

        for item in raw:
            if isinstance(item, str):
                name = item.strip()
                current_l1 = name
                current_l2 = None
                topics.append({"name": name, "level": 1, "parent": None})
            elif isinstance(item, dict):
                for l2_name, l2_children in item.items():
                    l2_name = l2_name.strip()
                    if current_l1 is None:
                        logger.warning(f"[topic] 二级标题缺少一级父级: {l2_name}")
                        continue
                    current_l2 = l2_name
                    topics.append(
                        {
                            "name": l2_name,
                            "level": 2,
                            "parent": current_l1,
                        }
                    )
                    if isinstance(l2_children, list):
                        for l3_item in l2_children:
                            if isinstance(l3_item, str):
                                topics.append(
                                    {
                                        "name": l3_item.strip(),
                                        "level": 3,
                                        "parent": l2_name,
                                    }
                                )
                            elif isinstance(l3_item, dict):
                                for l3_name in l3_item:
                                    topics.append(
                                        {
                                            "name": l3_name.strip(),
                                            "level": 3,
                                            "parent": l2_name,
                                        }
                                    )
        return topics

    # ============================================================
    # 构建主题树
    # ============================================================
    @staticmethod
    def build_topic_tree(topic_entries: list[dict]) -> list[dict]:
        """将扁平的主题条目列表构建为嵌套树

        输入: parse_topic_hierarchy() 的输出
        输出: 嵌套的 Level 1 → Level 2 → Level 3 树结构
        """
        tree = {}
        for entry in topic_entries:
            name = entry["name"]
            level = entry["level"]
            parent = entry.get("parent")

            if level == 1:
                if name not in tree:
                    tree[name] = {
                        "name": name,
                        "level": 1,
                        "parent": None,
                        "children": {},
                        "path": None,
                        "has_abstract": False,
                        "abstract_file": None,
                        "file_count": 0,
                    }
            elif level == 2:
                l1 = parent
                if l1 and l1 in tree:
                    if name not in tree[l1]["children"]:
                        tree[l1]["children"][name] = {
                            "name": name,
                            "level": 2,
                            "parent": l1,
                            "children": {},
                            "path": None,
                            "has_abstract": False,
                            "abstract_file": None,
                            "file_count": 0,
                        }
            elif level == 3:
                # 需要找到 L1 → L2 → 添加 L3
                for l1_name, l1_node in tree.items():
                    for l2_name, l2_node in l1_node["children"].items():
                        if l2_name == parent:
                            if name not in l2_node["children"]:
                                l2_node["children"][name] = {
                                    "name": name,
                                    "level": 3,
                                    "parent": l2_name,
                                    "children": {},
                                    "path": None,
                                    "file_count": 0,
                                }

        # 将 children dict 转为 list，并按排序
        result = []
        for l1_name in sorted(tree.keys()):
            l1 = tree[l1_name]
            l1_children = []
            for l2_name in sorted(l1["children"].keys()):
                l2 = l1["children"][l2_name]
                l2["children"] = sorted(l2["children"].values(), key=lambda x: x["name"])
                l1_children.append(l2)
            l1["children"] = l1_children
            result.append(l1)
        return result

    # ============================================================
    # 文件路径 → 主题映射
    # ============================================================
    @staticmethod
    def resolve_topic_from_path(file_path: str, workspace: str) -> list[dict]:
        """根据文件路径解析所属主题层级

        例如: Notes/普通人的 AI 学习指南/AI Agent 核心架构设计/MCP vs CLI/test.md
        → [{name: "普通人的 AI 学习指南", level: 1}, {name: "AI Agent 核心架构设计", level: 2}, {name: "MCP vs CLI", level: 3}]
        """
        topics = []
        try:
            rel = Path(file_path).relative_to(Path(workspace))
        except ValueError:
            return topics

        parts = rel.parts
        # 跳过 Notes/ 前缀
        if parts and parts[0] in ("Notes", "Organized"):
            parts = parts[1:]

        # 最多提取三层
        for i, part in enumerate(parts):
            if i >= MAX_LEVEL:
                break
            if i == len(parts) - 1 and Path(file_path).is_file():
                continue
            if i == 0:
                topics.append({"name": part, "level": 1, "parent": None})
            elif i == 1:
                parent = topics[0]["name"] if topics else None
                topics.append({"name": part, "level": 2, "parent": parent})
            elif i == 2:
                parent = topics[1]["name"] if len(topics) > 1 else None
                topics.append({"name": part, "level": 3, "parent": parent})

        return topics

    # ============================================================
    # 文件夹层级判定
    # ============================================================
    @staticmethod
    def determine_folder_level(parent_path: str, workspace: str) -> int:
        """判断新建文件夹应属于哪个层级

        规则：
        - Notes/ 下新建 → 一级
        - 一级文件夹下新建 → 二级
        - 二级文件夹下新建 → 三级
        - 三级文件夹下新建 → 不再作为标题（普通文件夹）
        """
        try:
            rel = Path(parent_path).relative_to(Path(workspace))
        except ValueError:
            return -1

        parts = [p for p in rel.parts if p not in ("Notes", "Organized")]

        if len(parts) == 0:
            return 1
        if len(parts) == 1:
            return 2
        if len(parts) == 2:
            return 3
        return -1

    # ============================================================
    # 删除保护
    # ============================================================
    @staticmethod
    def can_delete_topic(topic_name: str, level: int, tree: list[dict]) -> tuple[bool, str]:
        """检查是否可以删除某个主题

        规则：
        - 三级：可以直接删除
        - 二级：可以直接删除（但会同时删除其下的三级）
        - 一级：必须所有二级已删除才能删除
        """
        if level == 3:
            return True, ""

        # 找到该主题在树中的位置
        def find_node(nodes, name, lvl):
            for node in nodes:
                if node["name"] == name and node["level"] == lvl:
                    return node
                if node.get("children"):
                    result = find_node(node["children"], name, lvl)
                    if result:
                        return result
            return None

        if level == 1:
            node = find_node(tree, topic_name, 1)
            if node and node.get("children"):
                child_names = [c["name"] for c in node["children"]]
                return False, f"一级标题「{topic_name}」下仍有二级标题: {', '.join(child_names)}，请先删除它们"

        if level == 2:
            # 二级可以删除，但会级联删除其下三级（警告但允许）
            node = find_node(tree, topic_name, 2)
            if node and node.get("children"):
                child_names = [c["name"] for c in node["children"]]
                return True, f"将同时删除其下的三级标题: {', '.join(child_names)}"

        return True, ""

    # ============================================================
    # 综述控制
    # ============================================================
    @staticmethod
    def can_generate_abstract(topic_name: str, tree: list[dict], level: int = 0) -> tuple[bool, str]:
        """检查是否可以为某个标题生成综述

        规则：一级和二级不能同时有综述；三级不支持综述
        """
        # 三级标题无论如何都不支持综述
        if level == 3:
            return False, "三级标题不支持综述"

        def find_node(nodes, name):
            for node in nodes:
                if node["name"] == name:
                    return node
                if node.get("children"):
                    result = find_node(node["children"], name)
                    if result:
                        return result
            return None

        node = find_node(tree, topic_name)
        if not node:
            return False, f"标题「{topic_name}」不存在"

        level = node["level"]

        if level == 1:
            # 检查所有二级是否有综述
            for child in node.get("children", []):
                if child.get("has_abstract"):
                    return False, f"二级标题「{child['name']}」已设置有综述，一级不能再设"
            return True, ""

        if level == 2:
            # 检查其一级是否有综述
            parent_name = node.get("parent")
            if not parent_name:
                # 如果没有 parent 字段，在树中搜索
                for l1_node in tree:
                    for child in l1_node.get("children", []):
                        if child.get("name") == topic_name:
                            parent_name = l1_node["name"]
                            break
                    if parent_name:
                        break
            if parent_name:
                parent_node = find_node(tree, parent_name)
                if parent_node and parent_node.get("has_abstract"):
                    return False, f"一级标题「{parent_name}」已设置有综述，二级不能再设"
            return True, ""

        if level == 3:
            return False, "三级标题不支持综述"

        return True, ""

    # ============================================================
    # 文件系统扫描
    # ============================================================
    @staticmethod
    def collect_topic_labels(workspace: str) -> list[str]:
        """供下拉框使用的主题路径列表（仅目录遍历，不计文件数）。"""
        notes_dir = Path(workspace) / "Notes"
        if not notes_dir.exists():
            return []

        labels: list[str] = []
        for l1_dir in sorted(notes_dir.iterdir()):
            if not l1_dir.is_dir() or l1_dir.name.startswith("."):
                continue
            l1 = l1_dir.name
            labels.append(l1)

            for l2_dir in sorted(l1_dir.iterdir()):
                if not l2_dir.is_dir() or l2_dir.name.startswith("."):
                    continue
                l2_path = f"{l1}{TOPIC_SEP}{l2_dir.name}"
                labels.append(l2_path)

                for l3_dir in sorted(l2_dir.iterdir()):
                    if not l3_dir.is_dir() or l3_dir.name.startswith("."):
                        continue
                    labels.append(f"{l2_path}{TOPIC_SEP}{l3_dir.name}")

        return labels

    @staticmethod
    def build_tree_from_filesystem(workspace: str) -> list[dict]:
        """从文件系统扫描构建三层主题树（以实际文件夹为准，不依赖预定义列表）"""
        notes_dir = Path(workspace) / "Notes"
        if not notes_dir.exists():
            return []

        entries = []
        for l1_dir in sorted(notes_dir.iterdir()):
            if not l1_dir.is_dir() or l1_dir.name.startswith("."):
                continue
            entries.append({"name": l1_dir.name, "level": 1, "parent": None})

            for l2_dir in sorted(l1_dir.iterdir()):
                if not l2_dir.is_dir() or l2_dir.name.startswith("."):
                    continue
                entries.append({"name": l2_dir.name, "level": 2, "parent": l1_dir.name})

                for l3_dir in sorted(l2_dir.iterdir()):
                    if not l3_dir.is_dir() or l3_dir.name.startswith("."):
                        continue
                    entries.append({"name": l3_dir.name, "level": 3, "parent": l2_dir.name})

        tree = TopicManager.build_topic_tree(entries)

        wiki_dir = Path(workspace) / "wiki"

        for l1 in tree:
            l1_path = notes_dir / l1["name"]
            if l1_path.exists():
                l1["path"] = str(l1_path)
                survey = wiki_dir / f"{l1['name']}_综述.md"
                l1["has_abstract"] = survey.exists()
                l1["abstract_file"] = str(survey) if l1["has_abstract"] else None
                l1["file_count"] = TopicManager._count_files_in(l1_path)
            for l2 in l1.get("children", []):
                l2_path = notes_dir / l1["name"] / l2["name"]
                if l2_path.exists():
                    l2["path"] = str(l2_path)
                    survey = wiki_dir / f"{l2['name']}_综述.md"
                    l2["has_abstract"] = survey.exists()
                    l2["abstract_file"] = str(survey) if l2["has_abstract"] else None
                    l2["file_count"] = TopicManager._count_files_in(l2_path)
                for l3 in l2.get("children", []):
                    l3_path = notes_dir / l1["name"] / l2["name"] / l3["name"]
                    if l3_path.exists():
                        l3["path"] = str(l3_path)
                        l3["file_count"] = TopicManager._count_files_in(l3_path)

        return tree

    @staticmethod
    def _count_files_in(path: str | Path) -> int:
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return 0
        count = 0
        for f in p.iterdir():
            if f.is_file() and not f.name.startswith(".") and f.name not in ("综述.md", "WIKI.md", "tags.md"):
                count += 1
        return count

    # ============================================================
    # 序列化
    # ============================================================
    @staticmethod
    def tree_to_json(tree: list[dict]) -> list[dict]:
        """将主题树转为前端 JSON 格式（扁平化 children 为 list）"""
        result = []
        for l1 in tree:
            node = {
                "name": l1["name"],
                "level": 1,
                "parent": None,
                "path": l1.get("path"),
                "has_abstract": l1.get("has_abstract", False),
                "abstract_file": l1.get("abstract_file"),
                "file_count": l1.get("file_count", 0),
                "children": [],
            }
            for l2 in l1.get("children", []):
                l2_node = {
                    "name": l2["name"],
                    "level": 2,
                    "parent": l1["name"],
                    "path": l2.get("path"),
                    "has_abstract": l2.get("has_abstract", False),
                    "abstract_file": l2.get("abstract_file"),
                    "file_count": l2.get("file_count", 0),
                    "children": [],
                }
                for l3 in l2.get("children", []):
                    l3_node = {
                        "name": l3["name"],
                        "level": 3,
                        "parent": l2["name"],
                        "path": l3.get("path"),
                        "file_count": l3.get("file_count", 0),
                        "children": [],
                    }
                    l2_node["children"].append(l3_node)
                node["children"].append(l2_node)
            result.append(node)
        return result
