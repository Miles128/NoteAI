"""Auto-resolve same-name entity/concept pairs via batched LLM verdicts.

The semantic workbench surfaces ``cross_kind_duplicate`` quality issues
(one entity + one concept sharing a name fingerprint) into the Inbox.  This
module turns those pairs into a single batched LLM call and applies the
verdicts:

- ``merge_entity``: the concept is the same object → merge the concept into
  the entity (reusing ``entity_merge.merge_entities`` so mentions/relations/
  aliases move and the concept's name becomes an alias).
- ``merge_concept``: merge the entity into the concept.
- ``keep_both``: the two rows describe different things (entity = concrete
  product, concept = generic term) → keep both and mark the issue reviewed.
- ``skip``: leave the pair untouched for manual review.

Only pairs with a pending ``cross_kind_duplicate`` review_queue row are
processed, so re-running is idempotent and nothing outside the Inbox set is
touched.
"""

from __future__ import annotations

import json
import re
import time

from prompts import CROSS_KIND_RESOLVE_PROMPT
from sidecar.semantic.entity_merge import merge_entities
from sidecar.semantic.quality import quality_key
from sidecar.semantic.store import SemanticStore
from sidecar.semantic.store_objects import name_fingerprint

_VERDICTS = {"merge_entity", "merge_concept", "keep_both", "skip"}
_BATCH_SIZE = 40
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json_candidates(text: str) -> list[str]:
    """Yield balanced JSON object candidates that contain a pairs key."""
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
                if '"pairs"' in candidate:
                    candidates.append(candidate)
                start = -1
    return candidates


def parse_verdicts(raw: str) -> dict[int, str]:
    """Extract the pair_id → verdict map from an LLM output, tolerating
    fences, embedded JSON and partial batches. Pairs missing from the output
    are skipped (treated as manual review)."""
    text = (raw or "").strip()
    stripped = _FENCE.sub(r"\1", text).strip()
    candidates = [stripped] if stripped else []
    candidates.extend(_extract_json_candidates(text))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict) or not isinstance(parsed.get("pairs"), list):
            continue
        verdicts: dict[int, str] = {}
        for item in parsed["pairs"]:
            if not isinstance(item, dict):
                continue
            try:
                pair_id = int(item.get("pair_id"))
            except (TypeError, ValueError):
                continue
            verdict = str(item.get("verdict") or "").strip().lower()
            if verdict in _VERDICTS:
                verdicts[pair_id] = verdict
        return verdicts
    return {}


def collect_pairs(store: SemanticStore) -> list[dict]:
    """Same-name entity/concept pairs that have a pending cross_kind issue."""
    with store.connect() as conn:
        queued = {
            row["id"]
            for row in conn.execute(
                "SELECT id FROM review_queue WHERE item_kind = 'entity_quality' AND status = 'pending'"
            )
        }
        entities = [dict(row) for row in conn.execute("SELECT * FROM entities WHERE status = 'active'")]
        concepts = [dict(row) for row in conn.execute("SELECT * FROM concepts WHERE status = 'active'")]
        mention_counts = {
            (row["object_kind"], row["object_id"]): int(row["n"])
            for row in conn.execute(
                """SELECT object_kind, object_id, count(*) AS n FROM semantic_mentions
                   WHERE object_kind IN ('entity', 'concept') GROUP BY object_kind, object_id"""
            )
        }
    entity_by_fp: dict[str, list[dict]] = {}
    for entity in entities:
        entity_by_fp.setdefault(name_fingerprint(entity["canonical_name"]), []).append(entity)
    concept_by_fp: dict[str, list[dict]] = {}
    for concept in concepts:
        concept_by_fp.setdefault(name_fingerprint(concept["canonical_name"]), []).append(concept)

    pairs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for fp, entity_group in entity_by_fp.items():
        for entity in entity_group:
            for concept in concept_by_fp.get(fp, []):
                key = (entity["id"], concept["id"])
                if key in seen:
                    continue
                seen.add(key)
                issue_id = quality_key("cross_kind_duplicate", entity["id"], concept["id"])
                if issue_id not in queued:
                    continue
                pairs.append(
                    {
                        "pair_id": len(pairs) + 1,
                        "issue_id": issue_id,
                        "entity": entity,
                        "concept": concept,
                        "entity_mentions": mention_counts.get(("entity", entity["id"]), 0),
                        "concept_mentions": mention_counts.get(("concept", concept["id"]), 0),
                    }
                )
    return pairs


def build_prompt(pairs: list[dict]) -> str:
    lines = []
    for pair in pairs:
        entity = pair["entity"]
        concept = pair["concept"]
        lines.append(
            f"Pair {pair['pair_id']}:\n"
            f"  实体名: {entity['canonical_name']}\n"
            f"  实体类型: {entity.get('entity_type') or 'other'}\n"
            f"  实体描述: {entity.get('description') or '(空)'}\n"
            f"  实体出现次数: {pair['entity_mentions']}\n"
            f"  概念名: {concept['canonical_name']}\n"
            f"  概念描述: {concept.get('description') or '(空)'}\n"
            f"  概念出现次数: {pair['concept_mentions']}"
        )
    return CROSS_KIND_RESOLVE_PROMPT.format(candidates="\n\n".join(lines))


def _apply_verdict(store: SemanticStore, pair: dict, verdict: str, touched: dict) -> str:
    entity_id = pair["entity"]["id"]
    concept_id = pair["concept"]["id"]
    issue_id = pair["issue_id"]
    if verdict == "merge_entity":
        result = merge_entities(store, concept_id, entity_id, rebuild=False)
        if not result.get("success"):
            return result.get("message", "合并失败")
        touched["topics"].update(result.get("affected_topics", []))
        with store.connect() as conn:
            conn.execute(
                "UPDATE review_queue SET status = 'reviewed' WHERE id = ? AND status = 'pending'",
                (issue_id,),
            )
        return "概念已并入实体"
    if verdict == "merge_concept":
        result = merge_entities(store, entity_id, concept_id, rebuild=False)
        if not result.get("success"):
            return result.get("message", "合并失败")
        touched["topics"].update(result.get("affected_topics", []))
        return "实体已并入概念"
    if verdict == "keep_both":
        with store.connect() as conn:
            conn.execute(
                "UPDATE review_queue SET status = 'reviewed' WHERE id = ? AND status = 'pending'",
                (issue_id,),
            )
        return "保留双表"
    return "留待人工"


def _rebuild_once(store: SemanticStore, touched: dict) -> None:
    """Rebuild all semantic pages affected by a batch of merges, once."""
    from sidecar.semantic.object_wiki import materialize_object_collection
    from sidecar.semantic.topic_state import materialize_topic_state
    from sidecar.semantic.wiki import materialize_topic_wiki_page

    for topic in sorted(touched["topics"]):
        materialize_topic_state(store, topic)
        materialize_topic_wiki_page(store, topic)
    materialize_object_collection(store, "entity")
    if touched["concepts"]:
        materialize_object_collection(store, "concept")


def resolve_cross_kind_merges(
    store: SemanticStore,
    llm_call=None,
    *,
    batch_size: int = _BATCH_SIZE,
    dry_run: bool = False,
) -> dict:
    """Resolve pending cross-kind duplicate pairs with batched LLM verdicts.

    ``llm_call(prompt) -> str`` is injectable for tests; defaults to
    ``call_llm_raw``. Returns per-verdict stats and per-pair outcomes.
    """
    if llm_call is None:
        from utils.llm_utils import call_llm_raw

        def llm_call(prompt: str) -> str:
            return call_llm_raw(prompt, temperature=0.0)

    pairs = collect_pairs(store)
    if not pairs:
        return {"success": True, "total": 0, "outcomes": [], "stats": {}}
    if dry_run:
        return {
            "success": True,
            "total": len(pairs),
            "outcomes": [{"pair_id": p["pair_id"], "name": p["entity"]["canonical_name"]} for p in pairs],
            "stats": {},
            "dry_run": True,
        }

    stats: dict[str, int] = {"merge_entity": 0, "merge_concept": 0, "keep_both": 0, "skip": 0}
    outcomes: list[dict] = []
    touched: dict = {"topics": set(), "concepts": False}
    for start in range(0, len(pairs), batch_size):
        batch = pairs[start : start + batch_size]
        raw = ""
        try:
            raw = llm_call(build_prompt(batch))
        except Exception as exc:  # 单批失败不中断整体
            outcomes.append({"batch": start // batch_size, "error": str(exc)})
            continue
        verdicts = parse_verdicts(raw)
        for pair in batch:
            verdict = verdicts.get(pair["pair_id"], "skip")
            try:
                message = _apply_verdict(store, pair, verdict, touched)
            except Exception as exc:
                message = f"执行失败: {exc}"
                verdict = "skip"
            if verdict in {"merge_entity", "merge_concept"}:
                touched["concepts"] = True
            stats[verdict] = stats.get(verdict, 0) + 1
            outcomes.append(
                {
                    "pair_id": pair["pair_id"],
                    "name": pair["entity"]["canonical_name"],
                    "verdict": verdict,
                    "message": message,
                }
            )
        time.sleep(0.5)  # 批间限速
    try:
        _rebuild_once(store, touched)
    except Exception as exc:
        outcomes.append({"rebuild_error": str(exc)})
    return {"success": True, "total": len(pairs), "outcomes": outcomes, "stats": stats}


def stable_issue_id(entity_id: str, concept_id: str) -> str:
    """Public helper mirroring the quality rule id for tests/tooling."""
    return quality_key("cross_kind_duplicate", entity_id, concept_id)


__all__ = [
    "parse_verdicts",
    "collect_pairs",
    "build_prompt",
    "resolve_cross_kind_merges",
    "stable_issue_id",
]
