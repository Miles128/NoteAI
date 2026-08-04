"""Golden evaluation set for the Claim gate and evidence traceability.

This is the CI quality anchor promised by the PRD: every regression of the
deterministic Claim type gate (pseudo-claims leaking in, real judgments being
dropped) or of evidence resolvability fails the build with a measurable
accuracy report instead of a silent behavior drift.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from sidecar.semantic.compiler import compile_note_semantics
from sidecar.semantic.extractor import (
    _claim_has_required_judgment,
    extract_document_semantics,
    validate_extraction,
)
from sidecar.semantic.store import SemanticStore

# (statement, claim_type, expected_accept)
GOLDEN_GATE_CASES: list[tuple[str, str, bool]] = [
    # --- pseudo-claims that MUST be rejected --------------------------------
    ("混合检索结合了多种检索信号", "conclusion", False),
    ("该工具支持 75+ 模型", "conclusion", False),
    ("Python 3.10 发布于 2021 年", "conclusion", False),
    ("运行 uv sync 安装依赖", "conclusion", False),
    ("--port 参数用于指定端口", "conclusion", False),
    ("知识库是用于组织和管理知识的系统", "conclusion", False),
    ("该论文发表于 ACL 2024", "conclusion", False),
    ("嵌入向量维度为 512", "conclusion", False),
    ("该方法先分词，再编码，最后检索", "conclusion", False),
    ("API 以 JSON 格式返回结果", "conclusion", False),
    ("BM25 是一种经典的稀疏检索算法", "conclusion", False),
    ("系统需要 Node.js 18+ 环境运行", "conclusion", False),
    ("数据集包含 10 万条样本", "conclusion", False),
    ("Tauri 是一个桌面应用框架", "conclusion", False),
    ("作者是四海", "conclusion", False),
    ("实验使用了 8 块 A100 GPU", "conclusion", False),
    ("第三章介绍了检索的实现细节", "conclusion", False),
    ("索引重建大约需要 5 分钟", "conclusion", False),
    ("The library provides a REST API", "conclusion", False),
    ("The config file is located at ~/.noteai", "conclusion", False),
    ("嵌入向量维度为 512", "hypothesis", False),
    ("模型效果很好", "hypothesis", False),
    # --- round 2: attributes / definitions / counts / instructions ----------
    ("向量数据库使用 HNSW 索引", "conclusion", False),
    ("该项目采用 MIT 许可证", "conclusion", False),
    ("配置文件位于项目根目录", "conclusion", False),
    ("训练共进行了 200 个 epoch", "conclusion", False),
    ("函数接受两个参数并返回布尔值", "conclusion", False),
    ("RAG 的全称是检索增强生成", "conclusion", False),
    ("会议将于明年三月举行", "conclusion", False),
    ("该模块由三个子模块组成", "conclusion", False),
    ("数据集标注由五人团队完成", "conclusion", False),
    ("命令行工具的安装方式是 pip install", "conclusion", False),
    ("图表展示了各类别的分布", "conclusion", False),
    ("本文共分五章", "conclusion", False),
    ("作者的邮箱是 test@example.com", "conclusion", False),
    ("该接口每秒处理一千个请求", "conclusion", False),
    ("系统默认使用 8080 端口", "conclusion", False),
    ("实验在两个公开数据集上进行", "conclusion", False),
    ("该框架诞生于 2019 年", "conclusion", False),
    ("术语 embedding 指稠密向量表示", "conclusion", False),
    ("点击保存按钮提交表单", "conclusion", False),
    ("环境变量 API_KEY 用于鉴权", "conclusion", False),
    ("The model was trained on the C4 corpus", "conclusion", False),
    ("Table 2 lists the hyperparameters", "conclusion", False),
    ("The repository contains three modules", "conclusion", False),
    ("Retrieval happens after the reranking step", "conclusion", False),
    ("Users can export notes as PDF", "conclusion", False),
    # --- real judgments that MUST be accepted -------------------------------
    ("在该数据集上，混合检索优于纯向量检索", "conclusion", True),
    ("稀疏检索在关键词匹配场景中优于稠密检索", "conclusion", True),
    ("作者发现重排序器显著提升了前十命中率", "conclusion", True),
    ("由于数据稀疏，BM25 在长尾查询上表现较差", "conclusion", True),
    ("因此建议在生产环境使用混合加权", "conclusion", True),
    ("该方法将推理延迟降低了 30%", "conclusion", True),
    ("实验结果表明新方法更加稳健", "conclusion", True),
    ("模型规模是影响检索质量的关键", "conclusion", True),
    ("该方案不适合低资源场景", "conclusion", True),
    ("趋势显示本地知识库越来越重要", "conclusion", True),
    ("论文预测多模态检索将会成为主流", "conclusion", True),
    ("This method outperforms the baseline on BEIR", "conclusion", True),
    ("Increasing the batch size improves throughput", "conclusion", True),
    ("该发现说明稀疏表示在长文本上有优势", "conclusion", True),
    ("对比结果是 A 略劣于 B", "conclusion", True),
    ("持续训练的数据污染会导致性能虚高", "conclusion", True),
    ("增大上下文窗口会降低召回精度", "conclusion", True),
    ("该方法在开放域问答上效果优秀", "conclusion", True),
    # --- round 2: comparison / change / causal / recommendation --------------
    ("微调显著提升了小模型的指令跟随能力", "conclusion", True),
    ("相比全文检索，语义检索在问答场景更准确", "conclusion", True),
    ("长文档分块策略直接影响检索效果", "conclusion", True),
    ("缺少负样本会导致召回率虚高", "conclusion", True),
    ("该架构不适合实时推理场景", "conclusion", True),
    ("值得在更大规模语料上复现该结论", "conclusion", True),
    ("提示词工程对输出质量至关重要", "conclusion", True),
    ("结果显示蒸馏可以保留大部分能力", "conclusion", True),
    ("数据质量比模型规模更关键", "conclusion", True),
    ("该方法难以扩展到多语言场景", "conclusion", True),
    ("持续集成有助于保持代码质量", "conclusion", True),
    ("推理成本随模型规模增长而上升", "conclusion", True),
    ("研究发现早停可以防止过拟合", "conclusion", True),
    ("作者认为该基准不足以衡量真实能力", "conclusion", True),
    ("行业趋势表明代理应用正在爆发", "conclusion", True),
    ("预计明年多模态模型将进一步普及", "conclusion", True),
    ("This approach reduces inference cost significantly", "conclusion", True),
    ("Larger context windows lead to better factuality", "conclusion", True),
    ("The authors recommend a hybrid setup for production", "conclusion", True),
    ("Prompting alone is less effective than fine-tuning", "conclusion", True),
    ("缓存机制可以有效降低响应延迟", "conclusion", True),
    ("评测显示开源模型正在逼近闭源模型", "conclusion", True),
    ("对于初学者，推荐从提示词工程入手", "conclusion", True),
    ("该策略在长尾查询上尤其有效", "conclusion", True),
    ("实验证明量化带来的精度损失可以接受", "conclusion", True),
    # --- hypothesis gate -----------------------------------------------------
    ("更大的上下文窗口可能提升事实召回", "hypothesis", True),
    ("该现象可能由数据泄漏引起", "hypothesis", True),
    ("Knowledge graph augmentation could reduce hallucinations", "hypothesis", True),
    ("这一假设有待在更多数据集上验证", "hypothesis", True),
    ("如果检索语料的分布发生偏移，模型效果可能下降", "hypothesis", True),
    # --- round 2: hypothesis gate -------------------------------------------
    ("温度参数或许影响生成多样性", "hypothesis", True),
    ("推测该错误源于分词边界", "hypothesis", True),
    ("If the corpus is biased, the model may inherit that bias", "hypothesis", True),
    ("该机制也许能缓解灾难性遗忘", "hypothesis", True),
    ("We hypothesize that sparse attention scales linearly", "hypothesis", True),
    # --- hypothesis-labeled facts without hedging must be rejected ----------
    ("模型参数量为 70 亿", "hypothesis", False),
    ("检索阶段使用倒排索引", "hypothesis", False),
    ("The dataset was released in 2023", "hypothesis", False),
    ("提示词应包含任务说明", "hypothesis", False),
    ("该工具由开源社区维护", "hypothesis", False),
]


def test_claim_gate_golden_accuracy() -> None:
    """The deterministic gate must classify every golden case correctly."""
    mistakes = [
        (statement, claim_type, expected)
        for statement, claim_type, expected in GOLDEN_GATE_CASES
        if _claim_has_required_judgment(statement, claim_type) is not expected
    ]
    total = len(GOLDEN_GATE_CASES)
    accuracy = (total - len(mistakes)) / total
    assert not mistakes, f"Claim 门禁黄金集准确率 {accuracy:.1%}，误判 {len(mistakes)}/{total}：" + "; ".join(
        f"{s!r}({k}) 期望 {'接受' if e else '拒绝'}" for s, k, e in mistakes
    )


def test_claim_gate_requires_verbatim_evidence_quote() -> None:
    block = "在该数据集上，混合检索优于纯向量检索。"
    valid = validate_extraction(
        {
            "claims": [
                {
                    "statement": "混合检索优于纯向量检索",
                    "claim_type": "conclusion",
                    "scope": "",
                    "confidence": 0.9,
                    "evidence_quote": "混合检索优于纯向量检索",
                }
            ]
        },
        block_id="blk1",
        block_content=block,
    )
    assert len(valid["claims"]) == 1

    fabricated = validate_extraction(
        {
            "claims": [
                {
                    "statement": "混合检索优于纯向量检索",
                    "claim_type": "conclusion",
                    "scope": "",
                    "confidence": 0.9,
                    "evidence_quote": "原文中不存在这句话",
                }
            ]
        },
        block_id="blk1",
        block_content=block,
    )
    assert fabricated["claims"] == []


def test_code_blocks_never_produce_claims() -> None:
    result = validate_extraction(
        {
            "claims": [
                {
                    "statement": "该命令会提升构建速度",
                    "claim_type": "conclusion",
                    "scope": "",
                    "confidence": 0.9,
                    "evidence_quote": "uv sync",
                }
            ]
        },
        block_id="blk_code",
        block_content="uv sync --extra dev",
        block_type="code",
    )
    assert result["claims"] == []


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


def _active_claims(store: SemanticStore) -> list[dict]:
    with store.connect() as conn:
        return [dict(row) for row in conn.execute("SELECT id, statement FROM claims")]


def test_extraction_end_to_end_filters_pseudo_claims_and_keeps_evidence(tmp_path: Path) -> None:
    note = tmp_path / "Notes" / "RAG" / "混合检索评测.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(_NOTE_A, encoding="utf-8")

    compiled = compile_note_semantics(tmp_path, note)
    assert compiled["success"] is True

    llm = _make_llm(
        {
            "在该数据集上": {
                "concepts": [{"name": "混合检索", "description": "结合稀疏与稠密信号", "confidence": 0.9}],
                "entities": [{"name": "BM25", "type": "protocol", "description": "稀疏检索", "confidence": 0.9}],
                "claims": [
                    {
                        "statement": "在该数据集上，混合检索优于纯向量检索",
                        "claim_type": "conclusion",
                        "scope": "该数据集",
                        "confidence": 0.9,
                        "evidence_quote": "混合检索优于纯向量检索",
                    },
                    {
                        # Pseudo-claim: a definition-like restatement with a real
                        # quote. The gate must reject it despite the valid quote.
                        "statement": "混合检索结合了稀疏与稠密两种信号",
                        "claim_type": "conclusion",
                        "scope": "",
                        "confidence": 0.8,
                        "evidence_quote": "混合检索优于纯向量检索",
                    },
                ],
            },
            "该工具支持": {
                "concepts": [],
                "entities": [],
                "claims": [
                    {
                        # Attribute pseudo-claim from the tool description block.
                        "statement": "该工具支持 75+ 模型",
                        "claim_type": "conclusion",
                        "scope": "",
                        "confidence": 0.9,
                        "evidence_quote": "该工具支持 75+ 模型",
                    }
                ],
            },
        }
    )

    store = SemanticStore(tmp_path)
    result = extract_document_semantics(store, compiled["document_id"], llm_call=llm)
    assert result["failed"] == 0

    claims = _active_claims(store)
    statements = {claim["statement"] for claim in claims}
    assert statements == {"在该数据集上，混合检索优于纯向量检索"}, statements

    # Every surviving claim must resolve to an existing block with evidence.
    with store.connect() as conn:
        dangling = conn.execute(
            """SELECT e.id FROM evidence e
               WHERE NOT EXISTS (SELECT 1 FROM blocks b WHERE b.id = e.block_id)"""
        ).fetchall()
        claimless = conn.execute(
            """SELECT c.id FROM claims c
               WHERE NOT EXISTS (SELECT 1 FROM evidence e WHERE e.claim_id = c.id)"""
        ).fetchall()
    assert dangling == []
    assert claimless == []

    # The change log must expose the newly compiled knowledge.
    items, total = store.recent_changes(days=7)
    assert total > 0
    added_claims = [item for item in items if item["change_kind"] == "added" and item["object_kind"] == "claim"]
    assert added_claims and added_claims[0]["source_path"].endswith("混合检索评测.md")


def test_removing_source_paragraph_invalidates_claim_and_logs_change(tmp_path: Path) -> None:
    note = tmp_path / "Notes" / "RAG" / "混合检索评测.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(_NOTE_A, encoding="utf-8")

    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    llm = _make_llm(
        {
            "在该数据集上": {
                "concepts": [],
                "entities": [],
                "claims": [
                    {
                        "statement": "在该数据集上，混合检索优于纯向量检索",
                        "claim_type": "conclusion",
                        "scope": "",
                        "confidence": 0.9,
                        "evidence_quote": "混合检索优于纯向量检索",
                    }
                ],
            }
        }
    )
    extract_document_semantics(store, compiled["document_id"], llm_call=llm)
    assert len(_active_claims(store)) == 1

    # The author deletes the conclusion paragraph; recompilation must retire
    # the claim instead of leaving an unsupported statement in the workbench.
    note.write_text(
        "---\ntitle: 混合检索评测\ntopic: RAG > 检索\n---\n\n## 工具说明\n\n该工具支持 75+ 模型。\n",
        encoding="utf-8",
    )
    recompiled = compile_note_semantics(tmp_path, note)
    assert recompiled["success"] is True
    assert _active_claims(store) == []

    items, _total = store.recent_changes(days=7)
    invalidated = [item for item in items if item["change_kind"] == "invalidated" and item["object_kind"] == "claim"]
    assert invalidated, "删除证据段落后必须记录命题失效事件"
    assert invalidated[0]["detail"]["reason"] == "source_block_removed"
