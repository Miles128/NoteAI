"""Claim 联网证实/证伪：CLI 深度研究模式。

把命题交给第三方 CLI agent（claude/codex/gemini/kimi/opencode），由 agent
自带联网能力做多轮深度研究后，输出结构化判定
（verdict/confidence/summary/sources）写入 SemanticStore 的
claim_verifications 表，供语义工作台只读展示。

内置批量模式（verify_claims_batch）不依赖外部 agent：用项目自身 LLM 能力
批量判定命题真伪，结果同样写入 claim_verifications（method='llm'）。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from prompts import CLAIM_BATCH_VERIFY_PROMPT, CLAIM_VERIFY_CLI_PROMPT
from sidecar.semantic.store import SemanticStore

VERDICTS = {"supported", "refuted", "unclear"}
_VERDICT_LABELS = {"supported": "已证实", "refuted": "已证伪", "unclear": "存疑"}
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def verdict_label(verdict: str) -> str:
    return _VERDICT_LABELS.get(verdict, verdict)


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _extract_json_candidates(text: str) -> list[str]:
    """Yield balanced JSON object candidates that contain a verdict key."""
    candidates: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : index + 1]
                if '"verdict"' in candidate:
                    candidates.append(candidate)
                start = -1
    return candidates


def parse_verification_json(raw: str) -> dict:
    """Extract and validate the verdict JSON contract from an LLM/CLI output.

    Accepts bare JSON, JSON inside a Markdown fence, and JSON embedded in a
    longer agent transcript. Raises ValueError when no valid contract exists.
    """
    text = (raw or "").strip()
    stripped = _FENCE.sub("", text).strip()
    candidates = [stripped] if stripped else []
    candidates.extend(_extract_json_candidates(text))
    data: dict | None = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            data = parsed
            break
    if data is None:
        raise ValueError("未能从输出中解析出命题核查结果 JSON")

    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in VERDICTS:
        raise ValueError(f"verdict 必须是 {sorted(VERDICTS)} 之一，得到: {verdict or '空'}")
    sources = []
    for source in data.get("sources") or []:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url") or "").strip()
        title = str(source.get("title") or "").strip()
        if not url:
            continue
        item: dict[str, Any] = {"url": url}
        if title:
            item["title"] = title
        snippet = str(source.get("snippet") or "").strip()
        if snippet:
            item["snippet"] = snippet
        sources.append(item)
    return {
        "verdict": verdict,
        "confidence": _clamp(data.get("confidence")),
        "summary": str(data.get("summary") or "").strip(),
        "sources": sources[:10],
    }


def build_cli_research_prompt(claim: dict, context: str = "") -> str:
    return CLAIM_VERIFY_CLI_PROMPT.format(
        statement=claim["statement"],
        scope=claim.get("scope") or "（无）",
        context=context or "（无）",
    )


def _claim_source_context(store: SemanticStore, claim_id: str) -> str:
    """Brief source-file context for a claim (read-only, best effort)."""
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT DISTINCT d.title, d.path FROM evidence e
               JOIN blocks b ON b.id = e.block_id
               JOIN documents d ON d.id = b.document_id
               WHERE e.claim_id = ? LIMIT 3""",
            (claim_id,),
        ).fetchall()
    if not rows:
        return ""
    return "；".join(f"{row['title'] or row['path']}（{row['path']}）" for row in rows)


def check_cli_agent(agent_id: str) -> tuple[bool, str]:
    """Check whether a CLI agent is supported, installed, and keyed. Returns (ok, error)."""
    from sidecar.cli_agent.registry import get_registry

    registry = get_registry()
    for info in registry.list_agents():
        if info["id"] != agent_id:
            continue
        if not info["installed"]:
            return False, f"CLI agent {info['name']} 未安装（需要 {info['command']} 命令行工具），请先安装"
        agent = registry._get(agent_id)
        if agent is not None and not agent.has_api_key():
            keys = ", ".join(agent.env_keys or [])
            return False, f"CLI agent {info['name']} 缺少 API key（{keys}），请在环境变量或 NoteAI 设置中配置"
        return True, ""
    return False, f"不支持的 CLI agent: {agent_id}（可用：claude / codex / gemini / kimi / opencode）"


def verify_claim_via_cli(
    store: SemanticStore,
    claim: dict,
    *,
    agent_id: str,
    send_event: Any | None = None,
) -> dict:
    """CLI 模式：把命题交给 CLI agent 联网深度研究，解析判定并写入 store。"""
    from sidecar.cli_agent.registry import run_cli_agent

    ok, error = check_cli_agent(agent_id)
    if not ok:
        return {"success": False, "message": error}

    prompt = build_cli_research_prompt(claim, context=_claim_source_context(store, claim["id"]))
    result = run_cli_agent(agent_id, prompt, send_event=send_event)
    if not result.get("success"):
        return {
            "success": False,
            "message": result.get("message", "CLI agent 执行失败"),
            "output": result.get("output", ""),
        }
    output = result.get("output", "") or ""
    try:
        parsed = parse_verification_json(output)
    except ValueError as exc:
        return {
            "success": False,
            "message": f"CLI 深度研究已完成，但输出无法解析：{exc}",
            "output": output[-4000:],
        }
    verification = store.save_claim_verification(
        claim_id=claim["id"],
        verdict=parsed["verdict"],
        confidence=parsed["confidence"],
        summary=parsed["summary"],
        method="cli",
        agent=agent_id,
        sources=parsed["sources"],
    )
    return {"success": True, "verification": verification, "output": output}


def verify_statement_via_cli(
    statement: str,
    scope: str = "",
    *,
    agent_id: str,
    send_event: Any | None = None,
) -> dict:
    """对任意命题文本做 CLI 深度研究，不写入 store（即席使用）。"""
    from sidecar.cli_agent.registry import run_cli_agent

    ok, error = check_cli_agent(agent_id)
    if not ok:
        return {"success": False, "message": error}
    prompt = build_cli_research_prompt({"statement": statement, "scope": scope}, context="")
    result = run_cli_agent(agent_id, prompt, send_event=send_event)
    if not result.get("success"):
        return {
            "success": False,
            "message": result.get("message", "CLI agent 执行失败"),
            "output": result.get("output", ""),
        }
    output = result.get("output", "") or ""
    try:
        parsed = parse_verification_json(output)
    except ValueError as exc:
        return {"success": False, "message": f"CLI 深度研究已完成，但输出无法解析：{exc}", "output": output[-4000:]}
    return {"success": True, **parsed, "method": "cli", "agent": agent_id, "output": output}


def parse_batch_verification_json(raw: str) -> dict[int, dict]:
    """Extract claim_id → verdict dict from a batched LLM output.

    Tolerates fences, embedded JSON and partial batches; invalid entries are
    dropped (the claim is left unverified rather than mislabelled).
    """
    text = (raw or "").strip()
    stripped = _FENCE.sub("", text).strip()
    candidates = [stripped] if stripped else []
    candidates.extend(_extract_json_candidates(text))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict) or not isinstance(parsed.get("results"), list):
            continue
        results: dict[int, dict] = {}
        for item in parsed["results"]:
            if not isinstance(item, dict):
                continue
            try:
                claim_id = int(item.get("claim_id"))
            except (TypeError, ValueError):
                continue
            verdict = str(item.get("verdict") or "").strip().lower()
            if verdict not in VERDICTS:
                continue
            results[claim_id] = {
                "verdict": verdict,
                "confidence": _clamp(item.get("confidence")),
                "reason": str(item.get("reason") or "").strip()[:200],
            }
        return results
    return {}


def build_batch_verify_prompt(claims: list[dict]) -> str:
    lines = []
    for index, claim in enumerate(claims, 1):
        lines.append(
            f"Claim {index}:\n"
            f"  陈述: {claim['statement']}\n"
            f"  适用范围: {claim.get('scope') or '（无）'}"
        )
    return CLAIM_BATCH_VERIFY_PROMPT.format(claims="\n\n".join(lines))


def verify_claims_batch(
    store: SemanticStore,
    claims: list[dict],
    llm_call=None,
    *,
    batch_size: int = 40,
    agent: str = "builtin",
) -> dict:
    """内置批量命题真伪核查：分批 LLM 裁决并写入 claim_verifications。

    ``llm_call(prompt) -> str`` 可注入（测试用）；默认用 call_llm_raw。
    结果落库 method='llm'；单批失败不影响其他批。返回统计与明细。
    """
    if llm_call is None:
        from utils.llm_utils import call_llm_raw

        def llm_call(prompt: str) -> str:
            return call_llm_raw(prompt, temperature=0.0)

    if not claims:
        return {"success": True, "total": 0, "outcomes": [], "stats": {}}
    stats: dict[str, int] = {"supported": 0, "refuted": 0, "unclear": 0, "failed": 0}
    outcomes: list[dict] = []
    for start in range(0, len(claims), batch_size):
        batch = claims[start : start + batch_size]
        prompt = build_batch_verify_prompt(batch)
        raw = ""
        try:
            raw = llm_call(prompt)
        except Exception as exc:
            stats["failed"] += len(batch)
            outcomes.append({"batch": start // batch_size, "error": str(exc)})
            continue
        verdicts = parse_batch_verification_json(raw)
        # LLM 对每批输出批内序号 1..n，与 batch 内枚举对齐
        for index, claim in enumerate(batch, 1):
            result = verdicts.get(index)
            if result is None:
                stats["failed"] += 1
                outcomes.append(
                    {"claim_id": claim["id"], "statement": claim["statement"], "verdict": "missing"}
                )
                continue
            verification = store.save_claim_verification(
                claim_id=claim["id"],
                verdict=result["verdict"],
                confidence=result["confidence"],
                summary=result["reason"],
                method="llm",
                agent=agent,
            )
            stats[result["verdict"]] += 1
            outcomes.append(
                {
                    "claim_id": claim["id"],
                    "statement": claim["statement"],
                    "verdict": result["verdict"],
                    "confidence": result["confidence"],
                    "reason": result["reason"],
                    "saved": verification is not None,
                }
            )
        time.sleep(0.5)  # 批间限速
    return {"success": True, "total": len(claims), "outcomes": outcomes, "stats": stats}
