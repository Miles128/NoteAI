"""Ingest pipeline stages. Callables patched on ingest_pipeline are looked up at runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import config
from config.settings import NOTES_FOLDER, RAW_FOLDER
from sidecar.ingest_state import save_ingest_state


class Cancelled(Exception):
    pass


@dataclass
class IngestCtx:
    workspace: str
    mode: str
    file_paths: list[str] | None
    incremental: bool
    state: dict[str, Any]
    stats: dict[str, Any]
    affected_topics: set[str]
    converted_note_paths: list[str] = field(default_factory=list)
    indexed_paths: list[str] = field(default_factory=list)
    cancelled: Callable[[], bool] = lambda: False
    prog: Callable[..., None] = lambda *_a, **_k: None
    stage_done: Callable[[str], bool] = lambda _n: False
    mark_stage_done: Callable[[str], None] = lambda _n: None

    def persist(self) -> None:
        self.state["affected_topics"] = sorted(self.affected_topics)
        self.state["stats"] = self.stats
        save_ingest_state(self.state)


def _pipe():
    from sidecar import ingest_pipeline as m

    return m


def raise_if_cancelled(ctx: IngestCtx) -> None:
    if ctx.cancelled():
        raise Cancelled()


def run_convert_stage(ctx: IngestCtx) -> None:
    pipe = _pipe()
    if ctx.stage_done("convert"):
        ctx.prog("convert", 0.16, "跳过转换（已完成）")
        return
    if not ctx.incremental and not ctx.file_paths:
        pending_files = pipe._scan_convert_pending(ctx.workspace)
        if pending_files:
            ctx.prog("convert", 0.05, f"转换 {len(pending_files)} 个文件…")
            raw_path = str(Path(ctx.workspace) / RAW_FOLDER)
            conv = pipe.FileConverterManager()
            output_path = str(Path(ctx.workspace) / NOTES_FOLDER)
            results = conv.convert_batch(pending_files, output_path, raw_path=raw_path, assign_topic=False)
            ctx.stats["converted"] = sum(1 for r in results if r.get("success"))
            failed_conversions = [r for r in results if not r.get("success")]
            for r in results:
                if r.get("success") and r.get("output_path"):
                    out = Path(r["output_path"])
                    try:
                        ctx.converted_note_paths.append(str(out.relative_to(ctx.workspace)))
                    except ValueError:
                        ctx.converted_note_paths.append(r["output_path"])
            if failed_conversions:
                first_error = failed_conversions[0].get("error") or "未知错误"
                raise RuntimeError(f"文件转换失败 {len(failed_conversions)} 个: {first_error}")
        ctx.prog("convert", 0.16, f"转换完成: {ctx.stats['converted']} 个")
        ctx.mark_stage_done("convert")
        return
    ctx.prog("convert", 0.16, "无需转换")
    ctx.mark_stage_done("convert")


def run_compile_stage(ctx: IngestCtx) -> None:
    if ctx.stage_done("compile"):
        ctx.prog("compile", 0.28, "跳过笔记编译（已完成）")
        return
    from utils.note_compiler import compile_notes_batch, scan_compile_pending

    compile_targets: list[str] = list(ctx.converted_note_paths)
    if ctx.file_paths:
        ws_path = Path(ctx.workspace)
        for raw in ctx.file_paths:
            path = Path(raw)
            if not path.is_absolute():
                path = ws_path / raw
            if path.exists() and path.suffix.lower() == ".md":
                rel = str(path.relative_to(ws_path))
                if rel not in compile_targets:
                    compile_targets.append(rel)
    for rel in scan_compile_pending(ctx.workspace):
        if rel not in compile_targets:
            compile_targets.append(rel)

    if compile_targets:
        ctx.prog("compile", 0.17, f"笔记编译 ({len(compile_targets)} 篇)…")
        ctx.stats["compiled"], _ = compile_notes_batch(
            compile_targets,
            progress_cb=lambda cur, tot, msg: ctx.prog("compile", 0.17 + 0.11 * cur / max(tot, 1), msg),
        )
    ctx.prog("compile", 0.28, f"笔记编译完成: {ctx.stats['compiled']} 篇")
    ctx.mark_stage_done("compile")


def run_classify_stage(ctx: IngestCtx) -> None:
    pipe = _pipe()
    if ctx.stage_done("classify"):
        ctx.prog("classify", 0.45, "跳过分类（已完成）")
        return
    if ctx.incremental and not ctx.file_paths:
        to_classify = pipe._scan_classify_pending(ctx.workspace)
    elif ctx.file_paths:
        to_classify = []
        for raw in ctx.file_paths:
            path = Path(raw)
            if not path.is_absolute():
                path = Path(ctx.workspace) / raw
            if path.exists() and path.suffix.lower() == ".md":
                to_classify.append(path)
    else:
        to_classify = pipe._scan_classify_pending(ctx.workspace)
    total_c = max(len(to_classify), 1)
    classify_errors: list[str] = []
    for i, md in enumerate(to_classify):
        raise_if_cancelled(ctx)
        ctx.prog("classify", 0.28 + 0.17 * (i + 1) / total_c, f"分类 ({i + 1}/{len(to_classify)}): {md.name}")
        try:
            result = pipe.auto_assign_topic_for_file(str(md))
            if result and result.get("status") == "auto_assigned":
                t = result.get("topic", "")
                if t:
                    ctx.affected_topics.add(t)
                ctx.stats["classified"] += 1
            elif result and result.get("status") == "pending":
                ctx.stats["pending_topics"] += 1
            elif result and result.get("status") == "error":
                classify_errors.append(f"{md.name}: {result.get('message', '未知错误')}")
        except Exception as e:
            classify_errors.append(f"{md.name}: {e}")
    ctx.persist()
    if classify_errors:
        raise RuntimeError(f"分类失败 {len(classify_errors)} 篇: {'; '.join(classify_errors[:3])}")
    ctx.prog("classify", 0.45, f"分类完成: {ctx.stats['classified']} 篇，待确认 {ctx.stats['pending_topics']}")
    ctx.mark_stage_done("classify")


def run_placement(ctx: IngestCtx) -> None:
    from sidecar.topic_placement import auto_move_misplaced_notes

    placement_result = auto_move_misplaced_notes(ctx.workspace)
    placement_moves = placement_result.get("moved") or []
    ctx.stats["auto_topic_moves"] = len(placement_moves)
    for move in placement_moves:
        for topic in (move.get("current_topic"), move.get("suggested_topic")):
            if topic:
                ctx.affected_topics.add(str(topic))


def run_semantic_stage(ctx: IngestCtx) -> None:
    pipe = _pipe()
    if ctx.stage_done("semantic"):
        ctx.prog("semantic", 0.52, "跳过语义编译（已完成）")
        return
    if not config.semantic_compile_enabled:
        ctx.prog("semantic", 0.52, "语义编译已关闭")
        ctx.mark_stage_done("semantic")
        return
    from sidecar.semantic.compiler import compile_semantic_batch
    from sidecar.semantic.object_wiki import materialize_object_collection
    from sidecar.semantic.store import SemanticStore
    from sidecar.semantic.topic_state import materialize_topic_state
    from sidecar.semantic.wiki import materialize_topic_wiki_page
    from utils.note_scanner import iter_note_files

    store = SemanticStore(ctx.workspace)
    if ctx.incremental:
        semantic_targets = pipe._scan_index_pending(ctx.workspace)
        removed_topics = set(store.purge_missing_documents())
    else:
        semantic_targets = [md for md in iter_note_files(ctx.workspace) if "wiki" not in md.parts]
        removed_topics = set(store.purge_missing_documents(keep_paths=semantic_targets))
    if semantic_targets:
        semantic_stats = compile_semantic_batch(
            ctx.workspace,
            semantic_targets,
            progress_cb=lambda cur, tot, msg: ctx.prog("semantic", 0.45 + 0.07 * cur / max(tot, 1), msg),
            cancelled=ctx.cancelled,
        )
        ctx.stats["semantic_documents"] = semantic_stats["documents"]
        ctx.stats["semantic_blocks"] = semantic_stats["blocks"]
        ctx.stats["semantic_extracted_blocks"] = semantic_stats["extracted_blocks"]
        ctx.stats["semantic_failed_blocks"] = semantic_stats["failed_blocks"]
        ctx.stats["semantic_pending_documents"] = semantic_stats["pending_documents"]
        ctx.stats["semantic_failures"] = semantic_stats["failures"]
        semantic_topics = set(semantic_stats.get("affected_topics", semantic_stats["topics"])) | removed_topics
        ctx.affected_topics.update(semantic_topics)
        materialized = 0
        wiki_pages = 0
        for topic in sorted(semantic_topics):
            try:
                materialize_topic_state(store, topic)
                materialized += 1
                materialize_topic_wiki_page(store, topic)
                wiki_pages += 1
            except Exception as exc:
                ctx.stats["semantic_failures"].append({"topic": topic, "error": f"TopicState: {exc}"})
        ctx.stats["semantic_topic_states"] = materialized
        ctx.stats["semantic_wiki_pages"] = wiki_pages
    elif removed_topics:
        ctx.affected_topics.update(removed_topics)
        for topic in sorted(removed_topics):
            materialize_topic_state(store, topic)
            materialize_topic_wiki_page(store, topic)
        ctx.stats["semantic_topic_states"] = len(removed_topics)
        ctx.stats["semantic_wiki_pages"] = len(removed_topics)
    if removed_topics:
        for kind in ("entity", "concept"):
            try:
                materialize_object_collection(store, kind)
            except Exception as exc:
                ctx.stats["semantic_failures"].append({"object_collection": kind, "error": str(exc)})
    ctx.prog(
        "semantic",
        0.52,
        f"语义编译: {ctx.stats['semantic_documents']} 篇，失败块 {ctx.stats['semantic_failed_blocks']}",
    )
    ctx.persist()
    ctx.mark_stage_done("semantic")


def run_index_stage(ctx: IngestCtx) -> None:
    pipe = _pipe()
    if ctx.stage_done("index"):
        ctx.prog("index", 0.65, "跳过索引（已完成）")
        return
    ws_path = Path(ctx.workspace)
    purged_paths = pipe._purge_deleted_index_files(ctx.workspace)
    ctx.stats["purged_index_files"] = len(purged_paths)
    if ctx.incremental and not ctx.file_paths:
        index_targets = pipe._scan_index_pending(ctx.workspace)
    elif ctx.file_paths:
        index_targets = []
        for p in ctx.file_paths:
            path = Path(p)
            if not path.is_absolute():
                path = ws_path / p
            if path.exists() and path.suffix.lower() == ".md" and "wiki" not in path.parts:
                index_targets.append(path)
    else:
        index_targets = [
            md
            for md in ws_path.rglob("*.md")
            if not md.name.startswith(".")
            and "wiki" not in md.parts
            and not md.name.endswith("_综述.md")
            and NOTES_FOLDER in md.parts
        ]
    if index_targets:
        ctx.prog("index", 0.5, f"检查向量索引 ({len(index_targets)} 篇，仅更新有改动的)…")
        ctx.stats["indexed_files"], ctx.indexed_paths = pipe._index_markdown_files(
            ctx.workspace,
            index_targets,
            lambda cur, tot, msg: ctx.prog("index", 0.5 + 0.15 * cur / max(tot, 1), msg),
            ctx.cancelled,
        )
    ctx.prog("index", 0.65, f"索引更新: {ctx.stats['indexed_files']} 篇有改动")
    ctx.state["pending_crossref_paths"] = ctx.indexed_paths
    save_ingest_state(ctx.state)
    ctx.mark_stage_done("index")


def run_crossref_stage(ctx: IngestCtx) -> None:
    if ctx.stage_done("crossref"):
        ctx.prog("crossref", 0.7, "跳过交叉引用（已完成）")
        return
    raw_crossref_paths = ctx.state.get("pending_crossref_paths")
    resumed_crossref_paths = [str(path) for path in raw_crossref_paths] if isinstance(raw_crossref_paths, list) else []
    crossref_paths = ctx.indexed_paths or resumed_crossref_paths
    if crossref_paths and len(crossref_paths) > 1:
        from utils.link_indexer import discover_cross_refs_for_file

        total_x = len(crossref_paths)
        use_llm = total_x <= 20
        cross_added = 0
        crossref_errors: list[str] = []
        for i, rel in enumerate(crossref_paths):
            raise_if_cancelled(ctx)
            ctx.prog(
                "crossref",
                0.65 + 0.05 * (i + 1) / max(total_x, 1),
                f"交叉引用 ({i + 1}/{total_x}): {Path(rel).name}",
            )
            try:
                xr = discover_cross_refs_for_file(rel, use_llm=use_llm)
                cross_added += int(xr.get("added") or 0)
            except Exception as e:
                crossref_errors.append(f"{Path(rel).name}: {e}")
        ctx.stats["cross_refs"] = cross_added
        ctx.state["stats"] = ctx.stats
        save_ingest_state(ctx.state)
        if crossref_errors:
            raise RuntimeError(f"交叉引用失败 {len(crossref_errors)} 篇: {'; '.join(crossref_errors[:3])}")
    ctx.prog("crossref", 0.7, f"交叉引用完成: {ctx.stats.get('cross_refs', 0)} 条")
    ctx.mark_stage_done("crossref")


def run_cascade_stage(ctx: IngestCtx) -> None:
    if ctx.stage_done("cascade"):
        ctx.prog("cascade", 0.85, "跳过综述计划（已完成）")
        return
    from sidecar.workspace_rules import load_workspace_rules, resolve_survey_topic

    rules = load_workspace_rules()
    if rules.get("auto_update_survey", True):
        resolved = {resolve_survey_topic(t, rules.get("survey_at_level", 2)) for t in ctx.affected_topics}
        cascade_topics = sorted(resolved)
    else:
        cascade_topics = []
    if cascade_topics:
        ctx.stats["cascade_topics"] = cascade_topics
        ctx.prog("cascade", 0.85, f"已安排后台综述: {len(cascade_topics)} 个主题")
    else:
        ctx.prog("cascade", 0.85, "无需更新综述")
    ctx.mark_stage_done("cascade")


def run_lint_stage(ctx: IngestCtx) -> None:
    if ctx.stage_done("lint"):
        ctx.prog("lint", 0.92, "跳过健康检查（已完成）")
        return
    from sidecar.kb_lint import log_lint_report, run_kb_lint

    ctx.prog("lint", 0.88, "检查断链、孤儿页、过时综述…")
    lint_report = run_kb_lint(ctx.workspace)
    lint_summary = lint_report.get("summary", {})
    ctx.stats["lint"] = lint_summary if isinstance(lint_summary, dict) else {}
    log_lint_report(lint_report)
    lint_total = ctx.stats["lint"].get("total", 0)
    ctx.prog("lint", 0.92, f"Lint 完成: {lint_total} 项")
    ctx.mark_stage_done("lint")


def run_sync_stage(ctx: IngestCtx) -> None:
    pipe = _pipe()
    if ctx.stage_done("sync"):
        ctx.prog("sync", 1.0, "跳过同步（已完成）")
        return
    ctx.prog("sync", 0.95, "同步 WIKI.md…")
    pipe.sync_wiki_with_files()
    ctx.mark_stage_done("sync")
