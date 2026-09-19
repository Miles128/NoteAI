#!/usr/bin/env python3
"""RAG 黄金评测：20 题真评测 harness（P0 验证闭环）。

走生产对话路径（RagHandler._answer_with_rag），对 tests/fixtures/rag_gold_questions.yaml
的 20 道题逐题采集：题型识别、检索证据、引用、答案，输出人工打分表。

用法：
    # 检索层评测（无 LLM，不需要 API key；记录 prompt 组装与引用候选）
    uv run python scripts/rag_gold_eval.py --dry-run

    # 完整评测（LLM 真答案；key 从环境变量读取，或 --api-key 传入）
    OPENAI_API_KEY=sk-xxx uv run python scripts/rag_gold_eval.py

    # 冒烟（只跑前 3 题）
    uv run python scripts/rag_gold_eval.py --dry-run --limit 3

输出：--out 目录（默认 eval_reports/，已 gitignore）下的
    report_<mode>_<ts>.md   人工打分表（每题 3 个 0/1/2 评分列，留空待填）
    results_<mode>_<ts>.json  全量原始数据

打分维度（每题 0/1/2）：
    1. 答案正确性   答案是否正确、无明显编造
    2. 引用可定位   引用是否指向真实存在且相关的笔记
    3. 阅读引导     「接下来读哪几篇 / 还缺什么」类回答是否给出可执行的阅读路径
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

import yaml  # noqa: E402

QUESTIONS_FILE = ROOT / "tests" / "fixtures" / "rag_gold_questions.yaml"
SCORE_COLS = ["答案正确性", "引用可定位", "阅读引导"]


def load_questions() -> list[dict]:
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    questions = []
    for item in data:
        q = (item.get("q") or "").strip()
        if q:
            questions.append({"q": q, "expected": item.get("shape", "")})
    return questions


def make_handler(events: list):
    from sidecar.handlers.rag_handler import RagHandler

    from config import config

    return RagHandler(
        SimpleNamespace(
            _ctx=SimpleNamespace(config=config, logger=None),
            _send_response=lambda resp: events.append(resp),
        )
    )


def run_question(question: str, dry_run: bool) -> dict:
    """Run one gold question through the production RAG path."""
    from sidecar.rag.question_shape import classify_question_shape

    events: list = []
    handler = make_handler(events)

    # 兼容 #146 前后两种签名：旧版要求 use_vector_rag 关键字参数。
    import inspect

    kwargs: dict = {}
    if "use_vector_rag" in inspect.signature(handler._answer_with_rag).parameters:
        kwargs["use_vector_rag"] = True

    if dry_run:
        # 捕获 prompt 组装而不真正调用 LLM：记录 (prompt, kwargs)。
        import utils.llm_utils as llm

        captured: dict = {}
        original = llm.call_llm_raw_stream

        def fake_stream(prompt, **kwargs):
            captured["prompt"] = prompt
            captured["kwargs"] = {k: v for k, v in kwargs.items() if k != "chunk_callback"}
            return "【dry-run 占位答案——仅验证检索与 prompt 组装】"

        llm.call_llm_raw_stream = fake_stream
        try:
            result = handler._answer_with_rag({}, question, "", **kwargs)
        finally:
            llm.call_llm_raw_stream = original
        prompt = captured.get("prompt", "")
    else:
        result = handler._answer_with_rag({}, question, "", **kwargs)
        prompt = ""

    done = next(
        (
            e["result"]
            for e in reversed(events)
            if isinstance(e, dict) and e.get("result", {}).get("type") == "rag_chat_done"
        ),
        None,
    )
    meta = next(
        (e["result"] for e in events if isinstance(e, dict) and e.get("result", {}).get("type") == "rag_retrieval"),
        None,
    )
    debug = (meta or {}).get("data", {}).get("retrieval_debug", {})

    citations = (done or {}).get("citations", [])
    return {
        "question": question,
        "detected_shape": classify_question_shape(question),
        "success": bool(result.get("success")),
        "fail_message": "" if result.get("success") else str(result.get("message", "")),
        "retrieval": {
            "final": debug.get("final", 0),
            "raw_hits": debug.get("raw_hits", 0),
            "mmr_kept": debug.get("mmr_kept", 0),
            "hyde_enabled": debug.get("hyde_enabled", False),
        },
        "citations": [
            {
                "file": c.get("file_name") or Path(c.get("file_path") or "").name,
                "label": c.get("source_label", ""),
                "topic": c.get("topic", ""),
                "type": c.get("source_type", ""),
                "score": c.get("score"),
            }
            for c in citations
        ],
        "answer": (done or {}).get("answer", ""),
        "citation_quality": (done or {}).get("citation_quality", {}).get("level", ""),
        "prompt_chars": len(prompt),
        "prompt_head": prompt[:600],
    }


def render_markdown(questions: list[dict], records: list[dict], mode: str, elapsed: float) -> str:
    total = len(records)
    shape_ok = sum(1 for r in records if r["detected_shape"] == r["expected"])
    empty_retrieval = sum(1 for r in records if r["retrieval"]["final"] == 0)
    llm_ok = sum(1 for r in records if r["success"])
    lines = [
        "# RAG 黄金评测报告",
        "",
        f"- 模式：{'dry-run（检索层）' if mode == 'dryrun' else 'full（LLM 真答案）'}",
        f"- 题数：{total}　|　耗时：{elapsed:.1f}s",
        f"- 题型识别正确：{shape_ok}/{total}",
        f"- 检索为空：{empty_retrieval}/{total}",
        f"- LLM 调用成功：{llm_ok}/{total}" if mode != "dryrun" else "- （dry-run 不调用 LLM）",
        "",
        "## 打分表",
        "",
        "| # | 问题 | 期望题型 | 识别 | 检索 | 引用数 | 质量 | " + " | ".join(SCORE_COLS) + " |",
        "|---|------|----------|------|------|--------|------" + "------|" * len(SCORE_COLS),
    ]
    for i, r in enumerate(records, 1):
        lines.append(
            f"| {i} | {r['question'][:24]} | {r['expected']} | {r['detected_shape']} "
            f"| {r['retrieval']['final']} | {len(r['citations'])} | {r['citation_quality']} "
            + "| " * 0
            + " | ".join(["　"] * len(SCORE_COLS))
            + " |"
        )
    lines += ["", "## 逐题详情", ""]
    for i, r in enumerate(records, 1):
        lines.append(f"### {i}. {r['question']}")
        lines.append("")
        lines.append(
            f"- 期望 `{r['expected']}` / 识别 `{r['detected_shape']}`"
            f"　检索 {r['retrieval']['final']} 条（raw {r['retrieval']['raw_hits']}"
            f" → MMR {r['retrieval']['mmr_kept']}，HyDE={'on' if r['retrieval']['hyde_enabled'] else 'off'}）"
        )
        if r["fail_message"]:
            lines.append(f"- **失败**：{r['fail_message']}")
        if r["citations"]:
            lines.append("- 引用：")
            for c in r["citations"]:
                lines.append(
                    f"  - [{c['type']}] {c['file'] or c['label']}（{c['topic'] or '无主题'}，score={c['score']}）"
                )
        else:
            lines.append("- 引用：无")
        answer = r["answer"].strip()
        if mode == "dryrun" and r["prompt_head"]:
            lines.append(f"- prompt 组装：{r['prompt_chars']} 字符，证据预览：")
            lines.append("")
            lines.append("```")
            lines.append(r["prompt_head"])
            lines.append("```")
        elif answer:
            lines.append("")
            lines.append("> " + answer.replace("\n", "\n> "))
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 黄金评测 harness")
    parser.add_argument("--dry-run", action="store_true", help="只评测检索层与 prompt 组装，不调用 LLM")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题（0=全部）")
    parser.add_argument("--out", type=str, default=str(ROOT / "eval_reports"), help="报告输出目录")
    parser.add_argument("--workspace", type=str, default="", help="工作区路径（默认用 config 持久化值）")
    args = parser.parse_args()

    if args.workspace:
        from config import config

        config.workspace_path = args.workspace

    questions = load_questions()
    if args.limit > 0:
        questions = questions[: args.limit]
    mode = "dryrun" if args.dry_run else "full"
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    if not args.dry_run:
        # 完整模式依赖 LLM key：提前失败而不是跑完 20 题才发现。
        import os

        from utils import keyring_store

        has_key = bool(os.environ.get("OPENAI_API_KEY") or keyring_store.load_api_key())
        if not has_key:
            print("错误：完整模式需要 API key。设置 OPENAI_API_KEY 或用 --dry-run 先跑检索层。", file=sys.stderr)
            return 2

    print(f"评测开始：{len(questions)} 题，mode={mode}")
    records = []
    started = time.time()
    for i, item in enumerate(questions, 1):
        try:
            rec = run_question(item["q"], args.dry_run)
        except Exception as exc:  # 单题失败不中断整轮
            rec = {
                "question": item["q"],
                "expected": item["expected"],
                "detected_shape": "",
                "success": False,
                "fail_message": f"{type(exc).__name__}: {exc}",
                "retrieval": {"final": 0, "raw_hits": 0, "mmr_kept": 0, "hyde_enabled": False},
                "citations": [],
                "answer": "",
                "citation_quality": "",
                "prompt_chars": 0,
                "prompt_head": "",
            }
        rec["expected"] = item["expected"]
        records.append(rec)
        flag = "✓" if rec["success"] else "✗"
        print(f"  [{i}/{len(questions)}] {flag} {item['q'][:30]}  检索={rec['retrieval']['final']}")
    elapsed = time.time() - started

    json_path = out_dir / f"results_{mode}_{ts}.json"
    json_path.write_text(
        json.dumps({"mode": mode, "elapsed": elapsed, "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path = out_dir / f"report_{mode}_{ts}.md"
    md_path.write_text(render_markdown(questions, records, mode, elapsed), encoding="utf-8")

    print(f"\n完成：{elapsed:.1f}s")
    print(f"  打分表：{md_path}")
    print(f"  原始数据：{json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
