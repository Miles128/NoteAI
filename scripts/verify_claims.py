#!/usr/bin/env python3
"""对语义命题进行联网深度研究以证实或证伪（CLI 模式）。

把命题交给第三方 CLI agent（claude/codex/gemini/kimi/opencode）做联网深度研究，
由 agent 自行多轮检索与核对原文后给出结构化判定。

用法示例：
  uv run python scripts/verify_claims.py --list
  uv run python scripts/verify_claims.py --claim <claim_id> --agent claude
  uv run python scripts/verify_claims.py --statement "混合检索优于纯向量检索" --agent codex
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

from sidecar.semantic.claim_verifier import (  # noqa: E402
    verdict_label,
    verify_claim_via_cli,
    verify_statement_via_cli,
)
from sidecar.semantic.store import SemanticStore  # noqa: E402

from config import config  # noqa: E402


def _store() -> SemanticStore | None:
    workspace = config.workspace_path
    if not workspace:
        print("错误: 未设置工作区，请在 NoteAI 设置中选择工作区", file=sys.stderr)
        return None
    store = SemanticStore(workspace)
    store.initialize()
    if not store.path.exists():
        print("错误: 语义数据库初始化失败", file=sys.stderr)
        return None
    return store


def _print_verification(result: dict, claim: dict | None = None) -> None:
    if not result.get("success"):
        print(f"失败: {result.get('message', '未知错误')}", file=sys.stderr)
        output = result.get("output") or ""
        if output:
            print("--- CLI 输出片段 ---", file=sys.stderr)
            print(output[-2000:], file=sys.stderr)
        return
    verification = result.get("verification") or result
    verdict = verification.get("verdict", "unclear")
    print(f"判定: [{verdict_label(verdict)}] 置信度 {verification.get('confidence', 0):.2f}")
    if claim:
        print(f"命题: {claim.get('statement', '')}")
    summary = verification.get("summary") or ""
    if summary:
        print(f"总结: {summary}")
    sources = verification.get("sources") or []
    if sources:
        print("来源:")
        for source in sources[:8]:
            title = source.get("title") or source.get("url", "")
            print(f"  - {title}")
            print(f"    {source.get('url', '')}")
    if result.get("output"):
        print("--- CLI 原始输出尾部 ---")
        print((result["output"] or "")[-1500:])


def _list_claims(store: SemanticStore, args: argparse.Namespace) -> int:
    claims = store.list_claims_for_verification(topic=args.topic, limit=args.limit)
    if not claims:
        print("当前没有可验证的命题（无 active 且有证据的 Claim）。")
        return 0
    print(f"命题验证状态（共 {len(claims)} 条）：")
    for item in claims:
        verification = item.get("verification")
        statement = item.get("statement", "")
        scope = f"（{item.get('scope')}）" if item.get("scope") else ""
        if verification:
            label = verdict_label(verification.get("verdict", "unclear"))
            method = verification.get("method", "")
            agent = verification.get("agent") or ""
            suffix = f"  via {agent}" if agent else ""
            print(f"  [{label}] {statement}{scope}  [{method}{suffix}]")
        else:
            print(f"  [未验证] {statement}{scope}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true", help="列出命题与验证状态")
    parser.add_argument("--claim", metavar="ID", help="验证指定命题 ID（须搭配 --agent，落库）")
    parser.add_argument("--statement", metavar="TEXT", help="直接验证命题文本（须搭配 --agent，不落库）")
    parser.add_argument("--agent", metavar="CLI", help="CLI agent（claude/codex/gemini/kimi/opencode），联网深度研究")
    parser.add_argument("--topic", metavar="TOPIC", help="列表时按主题过滤")
    parser.add_argument("--limit", type=int, metavar="N", help="列表时最多显示条数")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args()

    modes = [args.list, bool(args.claim), bool(args.statement)]
    if sum(modes) != 1:
        parser.error("--list / --claim / --statement 必须且只能指定一个")
    if args.claim or args.statement:
        if not args.agent:
            parser.error("--claim / --statement 必须搭配 --agent（CLI 深度研究模式）")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit 必须为正整数")

    store = _store()
    if store is None:
        return 2

    if args.list:
        return _list_claims(store, args)

    if args.claim:
        claims = store.list_claims_for_verification(limit=2000)
        claim = next((item for item in claims if item["id"] == args.claim), None)
        if claim is None:
            print(f"错误: 未找到命题 {args.claim}（仅支持 active 且有证据的命题）", file=sys.stderr)
            return 2
        result = verify_claim_via_cli(store, claim, agent_id=args.agent)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, default=list))
        else:
            _print_verification(result, claim)
        return 0 if result.get("success") else 1

    if args.statement:
        result = verify_statement_via_cli(args.statement, agent_id=args.agent)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, default=list))
        else:
            _print_verification(result)
        return 0 if result.get("success") else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
