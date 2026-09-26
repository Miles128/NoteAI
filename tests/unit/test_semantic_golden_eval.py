"""Golden evaluation set for the deterministic object-name noise gate.

This is the CI quality anchor promised by the PRD: every regression of the
deterministic noise gate (noise names leaking in, real objects being dropped)
fails the build with a measurable accuracy report instead of a silent
behavior drift.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from sidecar.semantic.compiler import compile_note_semantics
from sidecar.semantic.extractor import (
    _is_noise_object_name,
    extract_document_semantics,
)
from sidecar.semantic.store import SemanticStore

_NOTE_A = """---
title: 混合检索评测
topic: RAG > 检索
---

## 结论

在该数据集上，混合检索优于纯向量检索，作者发现重排序器显著提升了前十命中率。

## 工具说明

该工具支持 75+ 模型。运行 uv sync 安装依赖。
"""


def _make_llm(outputs: dict[str, dict]) -> Callable[[str], str]:
    def llm_call(prompt: str) -> str:
        for marker, payload in outputs.items():
            if marker in prompt:
                return json.dumps(payload, ensure_ascii=False)
        return json.dumps({"concepts": [], "entities": [], "claims": []})

    return llm_call


NOISE_NAMES = [
    # 文件名 / 路径
    "SKILL.md",
    "prepare.py",
    "program.md",
    "03_产品方法论/08_AI产品测试设计与测试用例设计.md",
    # 隐藏文件 / 目录
    ".env",
    ".gitignore",
    ".claude/CLAUDE.md",
    ".worktrees/myrepo-auth",
    # 命令参数 / 临时命名
    "--ar",
    "--style raw",
    "-s",
    "_private",
    # 序号前缀（文件名 / 章节标题样式）
    "06_四阶十二步法",
    "08_AI产品测试设计",
    "01-基础",
    "1.2_进阶",
    # 多对象合并名（斜杠 / 全角斜杠 / 顿号）
    "GPT-4o/5",
    "DeepSeek V3/R1",
    "华佗（华为）/ 润达医疗大模型",
    "创客贴/来画/水母智能/Nui",
    "Build/Buy/Bake",
    # 域名 / 纯版本号 / 纯符号
    "learnprompting.org",
    "2.5.1",
    "12345",
    "...",
    # HTTP 状态码被抽成"协议实体"
    "200 OK",
    "201 Created",
    "301 永久搬家",
    "404 找不到",
    "500 服务器炸了",
    "503 服务不可用",
    # 引文 / 论文标题
    "Rumelhart, Hinton & Williams (1986)",
    "Hochreiter & Schmidhuber (1997)",
    "He, K., et al. (2015). Delving Deep into Rectifiers. ICCV 2015",
    "Andrej Karpathy. A Recipe for Training Neural Networks (2019)",
    "Are Emergent Abilities a Mirage? (Schaeffer et al., 2023)",
    "Batch Normalization（2015）",
    # 随机混合码 / 股票代码
    "5038HVQRHO",
    "AEARMS3JN0",
    "S9XTOGN1W1",
    "SH600519",
    # 中文量纲 / 数量短语
    "200 份 JD 真相",
    "200个AI产品经理JD",
    "420亿美元",
    "500+ AI Agent Projects",
    # 英文常用词（黑名单门禁）
    "fetch",
    "local",
    "bundled",
    "managed",
    "manifesting",
    "interrupt",
    "researcher",
    "reviewer",
    "writer",
    "amount",
    "city",
    "unit",
    "users",
    "orders",
    "todos",
    "search",
    "calculator",
    "finalize",
    "coder",
    "main",
    "only",
    "vibe",
    "vision",
    "warmup",
    "border",
    "margin",
    "padding",
    "gap",
    "plugin",
    "inline",
    "ignore",
    "approval",
    "filesystem",
    "source",
    "description",
    "data",
    "model",
    "system",
    "output",
    "status",
]

VALID_NAMES = [
    "RAG",
    "模型",
    "BM25",
    "混合检索",
    "GLM 5.2",
    "Grok 4.5",
    "DeepSeek V3.2",
    "Qwen2.5-7B",
    "36 氪",
    "11 Labs",
    "Claude Code",
    ".NET",
    ".NET Core",
    "MCP Server",
    "ChatBot",
    "Anthropic",
    # 白名单放行的英文专名（库/工具/算子名）
    "pandas",
    "numpy",
    "curl",
    "jieba",
    "matplotlib",
    "pgvector",
    "postgres",
    "fastapi",
    "pytorch",
    "tensorflow",
    "redis",
    "kafka",
    "tiktoken",
    "dotenv",
    "ripgrep",
    "pyenv",
    "pnpm",
    "yarn",
    "uvicorn",
    "helm",
    "tanh",
    "grad",
    "vmap",
]


def test_noise_object_name_gate_keeps_valid_objects() -> None:
    """Deterministic noise gate must reject every noise pattern above."""
    rejected = [name for name in NOISE_NAMES if not _is_noise_object_name(name)]
    assert not rejected, f"以下噪声名漏过门禁: {rejected}"


def test_noise_object_name_gate_keeps_real_objects() -> None:
    """Versioned model names, orgs and capitalised products must survive."""
    dropped = [name for name in VALID_NAMES if _is_noise_object_name(name)]
    assert not dropped, f"以下真实对象被误杀: {dropped}"


def test_prompt_version_advances_with_rules_changes() -> None:
    """提示词规则（OBJECT_NAME_RULES）与 PROMPT_VERSION 必须联动：
    任何规则变更都必须递增版本号，否则存量块不会重抽，新规则形同虚设。"""
    from sidecar.semantic.extractor import PROMPT_VERSION

    from prompts import SEMANTIC_OBJECT_NAME_RULES

    assert PROMPT_VERSION >= 7, "PROMPT_VERSION 必须随提示词规则变更递增（当前规则为 v7）"
    assert "所有英文常用词不得输出" in SEMANTIC_OBJECT_NAME_RULES
    assert "实体与概念的区别" in SEMANTIC_OBJECT_NAME_RULES


def test_noise_names_never_reach_storage(tmp_path: Path) -> None:
    """Noise names must be filtered by validate_extraction, not persisted."""
    note = tmp_path / "Notes" / "AI" / "噪声.md"
    note.parent.mkdir(parents=True)
    note.write_text("# 噪声\n\n## 工具\n\n使用 --ar 参数与 prepare.py 脚本。\n", encoding="utf-8")
    compiled = compile_note_semantics(tmp_path, note)
    assert compiled["success"] is True
    store = SemanticStore(tmp_path)

    def llm(_prompt: str) -> str:
        return json.dumps(
            {
                "concepts": [{"name": "混合检索", "description": "组合检索", "confidence": 0.9}],
                "entities": [
                    {"name": "--ar", "type": "other", "description": "参数", "confidence": 0.9},
                    {"name": "prepare.py", "type": "artifact", "description": "脚本", "confidence": 0.9},
                    {"name": "BM25", "type": "other", "description": "算法", "confidence": 0.9},
                ],
                "claims": [],
            }
        )

    extract_document_semantics(store, compiled["document_id"], llm_call=llm)
    with store.connect() as conn:
        names = [row["canonical_name"] for row in conn.execute("SELECT canonical_name FROM entities")]
    assert "BM25" in names
    assert "--ar" not in names
    assert "prepare.py" not in names


def test_deactivate_noise_objects_cleans_legacy_rows(tmp_path: Path) -> None:
    """Legacy noise written before the gate must be deactivated with audit."""
    store = SemanticStore(tmp_path)
    store.initialize()
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO documents(id, path, content_hash, title, topic, compiled_at) "
            "VALUES('doc-n', 'Notes/AI/x.md', 'h', 'x', 'AI', '2026-07-17T10:00:00Z')"
        )
        conn.execute(
            "INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal, "
            "content, content_hash, start_line, end_line) "
            "VALUES('block-n', 'doc-n', 'paragraph', '[]', 0, '内容', 'bh', 1, 1)"
        )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('ent-n1', '--ar', 'other', '参数', 0.9, 'active')"
        )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('ent-n2', 'BM25', 'algorithm', '算法', 0.9, 'active')"
        )
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('con-n1', 'prepare.py', '脚本', 0.9, 'active')"
        )
        conn.execute("INSERT INTO semantic_mentions VALUES('ent-n1', 'entity', 'block-n')")
        conn.execute("INSERT INTO semantic_mentions VALUES('ent-n2', 'entity', 'block-n')")
        conn.execute("INSERT INTO semantic_mentions VALUES('con-n1', 'concept', 'block-n')")
        conn.execute(
            "INSERT INTO relations(id, source_id, relation_type, target_id, confidence, block_id) "
            "VALUES('rel-n', 'ent-n1', 'RELATED_TO', 'con-n1', 0.8, 'block-n')"
        )

    stats = store.deactivate_noise_objects()
    assert stats == {"entities": 1, "concepts": 1}
    with store.connect() as conn:
        assert conn.execute("SELECT status FROM entities WHERE id='ent-n1'").fetchone()[0] == "inactive"
        assert conn.execute("SELECT status FROM entities WHERE id='ent-n2'").fetchone()[0] == "active"
        assert conn.execute("SELECT status FROM concepts WHERE id='con-n1'").fetchone()[0] == "inactive"
        assert conn.execute("SELECT count(*) FROM semantic_mentions WHERE object_id='ent-n1'").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM relations WHERE id='rel-n'").fetchone()[0] == 0
        audit = conn.execute("SELECT count(*) FROM semantic_change_log WHERE change_kind='deactivated'").fetchone()[0]
    assert audit == 2

    # Idempotent: a second pass must not touch anything.
    assert store.deactivate_noise_objects() == {"entities": 0, "concepts": 0}
