"""Claim 联网证实/证伪：CLI 深度研究 + 内置 LLM 推理双模式。

CLI 模式：把命题交给第三方 CLI agent（claude/codex/gemini/kimi/opencode），
由 agent 自带联网能力做多轮深度研究后，输出结构化判定
（verdict/confidence/summary/sources）写入 SemanticStore 的
claim_verifications 表，供语义工作台只读展示。

内置 LLM 模式（verify_claim_via_llm）不依赖外部 agent：用项目自身 LLM 能力
（DeepSeek reasoning）流式判定单条命题真伪，结果同样写入
claim_verifications（method='llm'）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from prompts import CLAIM_BATCH_VERIFY_PROMPT, CLAIM_VERIFY_CLI_PROMPT
from sidecar.semantic.store import SemanticStore


def _opencode_model_params() -> tuple[str | None, str | None]:
    """决定 opencode agent 的模型与推理强度。

    优先级：
    1. NoteAI 配置中的 model_name（用户在设置里选择的模型）——若格式为
       provider/model 则直接使用；
    2. 纯模型名（如 deepseek-v4-flash）——探测用户 opencode 已认证的
       provider（auth.json），组合成 provider/model；无可用 provider 时
       返回 (None, 'high')，让 opencode 用自身默认路由。
    3. 未配置模型时返回 (None, 'high')。

    推理强度固定 high：联网深度研究需要较强的 reasoning。
    """
    from config import config as _config

    model = (getattr(_config, "model_name", "") or "").strip()
    if not model:
        return None, "high"
    if "/" in model:
        return model, "high"
    provider = _opencode_auth_providers()
    if provider and _model_matches_provider(model, provider):
        return f"{provider}/{model}", "high"
    return None, "high"


def _model_matches_provider(model: str, provider: str) -> bool:
    """模型名是否属于该 provider 家族（deepseek 模型含 deepseek 字样等）。"""
    model_l = model.casefold()
    provider_l = provider.casefold()
    family = {
        "deepseek": ("deepseek",),
        "opencode": ("opencode", "deepseek", "gpt", "claude", "sonnet", "opus"),
        "opencode-go": ("deepseek", "gpt", "claude", "sonnet", "opus"),
        "openai": ("gpt", "o1", "o3", "o4"),
        "anthropic": ("claude", "sonnet", "opus", "haiku"),
    }
    keywords = family.get(provider_l, (provider_l,))
    return any(kw in model_l for kw in keywords)


def _opencode_auth_providers() -> str | None:
    """返回用户 opencode 已认证的第一个 provider 名（auth.json）。"""
    import os
    from pathlib import Path

    candidates = []
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        candidates.append(Path(xdg) / "opencode" / "auth.json")
    candidates.append(Path.home() / ".local" / "share" / "opencode" / "auth.json")
    candidates.append(Path.home() / "Library" / "Application Support" / "opencode" / "auth.json")
    for path in candidates:
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            providers = [k for k in data if k not in ("version", "type")]
            if providers:
                return providers[0]
        except (OSError, ValueError):
            continue
    return None


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
    result = run_cli_agent(
        agent_id,
        prompt,
        send_event=send_event,
        # CLI 深度研究实测约 5-6 分钟；硬超时须小于 Rust 侧
        # verify_semantic_claim 的 900s 窗口，保证超时即终止、RPC 内返回失败。
        timeout=840.0,
        # opencode 默认路由可能随机选到不可用模型（gpt-5.3-chat 曾 840s 零输出）；
        # 优先使用 NoteAI 配置的模型（用户可自行选择），未配置则交给 opencode 路由。
        model=(_opencode_model_params()[0] if agent_id == "opencode" else None),
        variant=(_opencode_model_params()[1] if agent_id == "opencode" else None),
    )
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
    result = run_cli_agent(
        agent_id,
        prompt,
        send_event=send_event,
        timeout=840.0,
        model=_opencode_model_params()[0] if agent_id == "opencode" else None,
        variant=_opencode_model_params()[1] if agent_id == "opencode" else None,
    )
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


def verify_claim_via_llm(
    store: SemanticStore,
    claim: dict,
    *,
    send_event: Any | None = None,
    temperature: float = 0.0,
) -> dict:
    """内置 LLM 模式：单条命题用 DeepSeek reasoning 流式核查，结果落库。

    判定过程经 send_event 推送 ``verify_llm_output``（token 增量）与
    ``verify_llm_done``（完成摘要）事件，供前端实时展示研究进度。
    与 verify_claims_batch 共用批量判定提示词（单条 batch），
    method='llm' 落库，agent='api'。
    """
    from utils.llm_utils import call_llm_raw_stream

    def _emit(event: dict) -> None:
        if send_event is None:
            return
        try:
            send_event(event)
        except Exception:
            pass

    _emit({"type": "verify_llm_start", "claim_id": claim["id"], "statement": claim["statement"]})
    prompt = build_batch_verify_prompt([claim])
    chunks: list[str] = []

    def _on_chunk(chunk: str) -> None:
        chunks.append(chunk)
        _emit({"type": "verify_llm_output", "claim_id": claim["id"], "content": chunk})

    try:
        raw = call_llm_raw_stream(
            prompt,
            temperature=temperature,
            disable_thinking=False,  # 命题核查是判断类任务：显式走 DeepSeek reasoning
            chunk_callback=_on_chunk,
        )
    except Exception as exc:
        _emit({"type": "verify_llm_error", "claim_id": claim["id"], "error": str(exc)})
        return {"success": False, "message": f"LLM 核查失败: {exc}"}

    full = "".join(chunks) or raw
    try:
        verdicts = parse_batch_verification_json(full)
    except ValueError as exc:
        _emit({"type": "verify_llm_error", "claim_id": claim["id"], "error": str(exc)})
        return {"success": False, "message": f"LLM 输出无法解析: {exc}", "output": full[-2000:]}
    result = verdicts.get(1) or {}
    verdict = result.get("verdict")
    if verdict not in ("supported", "refuted", "unclear"):
        _emit({"type": "verify_llm_error", "claim_id": claim["id"], "error": "verdict 无效"})
        return {"success": False, "message": "LLM 输出缺少有效 verdict", "output": full[-2000:]}
    verification = store.save_claim_verification(
        claim_id=claim["id"],
        verdict=verdict,
        confidence=result.get("confidence", 0.5),
        summary=result.get("reason", ""),
        method="llm",
        agent="api",
    )
    _emit(
        {
            "type": "verify_llm_done",
            "claim_id": claim["id"],
            "verdict": verdict,
            "confidence": result.get("confidence", 0.5),
            "reason": result.get("reason", ""),
        }
    )
    return {"success": True, "verification": verification, "output": full}


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
                raw_claim_id = item.get("claim_id")
                claim_id = int(raw_claim_id) if raw_claim_id is not None else None
            except (TypeError, ValueError):
                continue
            verdict = str(item.get("verdict") or "").strip().lower()
            if verdict not in VERDICTS or claim_id is None:
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
        lines.append(f"Claim {index}:\n  陈述: {claim['statement']}\n  适用范围: {claim.get('scope') or '（无）'}")
    return CLAIM_BATCH_VERIFY_PROMPT.format(claims="\n\n".join(lines))
