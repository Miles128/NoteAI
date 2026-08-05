"""One-time migration: merge per-topic semantic cards into top-level merged pages.

What it does:
1. Re-materializes one merged `wiki/semantic/{顶层}_语义.md` per top-level topic
   (descendant topics become nested sections inside the merged file).
2. Removes legacy nested card files (`semantic/A/B/C_语义.md`) and empty dirs,
   keeping the top-level merged cards plus `概念.md` / `实体.md`.
3. Injects semantic-card links into `WIKI.md` bookshelf sections (idempotent).

Safe by design: everything under `wiki/semantic/` is a derived artifact that can
be rebuilt from semantic.db, so removal is lossless. Prints a summary; use
`--dry-run` to preview without writing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))

from config import config  # noqa: E402


def _resolve_workspace(args_workspace: str | None) -> Path:
    if args_workspace:
        return Path(args_workspace)
    ws = Path(config.workspace_path or "")
    if ws.exists():
        return ws
    raise SystemExit("未找到工作区：请用 --workspace 指定，或先设置 config.workspace_path")


def main() -> None:
    parser = argparse.ArgumentParser(description="合并语义知识卡片为顶层主题文件")
    parser.add_argument("--workspace", default=None, help="工作区路径（默认取 config.workspace_path）")
    parser.add_argument("--dry-run", action="store_true", help="只预览不写入")
    args = parser.parse_args()

    workspace = _resolve_workspace(args.workspace)
    from sidecar.semantic.store import SemanticStore
    from sidecar.semantic.wiki import materialize_topic_wiki_page, top_level_topic
    from sidecar.wiki_utils import sync_semantic_links

    store = SemanticStore(workspace)
    db = store.path
    if not db.exists():
        raise SystemExit(f"语义数据库不存在：{db}")

    with store.connect() as conn:
        topic_rows = conn.execute("SELECT DISTINCT topic FROM documents WHERE topic != ''").fetchall()
    tops = sorted({top_level_topic(row["topic"]) for row in topic_rows})
    print(f"顶层主题 {len(tops)} 个：{', '.join(tops)}")

    semantic_dir = workspace / "wiki" / "semantic"
    if not args.dry_run:
        for top in tops:
            target = materialize_topic_wiki_page(store, top)
            print(f"  已重建：{target.relative_to(workspace)}")
    else:
        print(f"  [dry-run] 将重建：semantic/{{顶层}}_语义.md × {len(tops)}")

    if not semantic_dir.exists():
        print("语义目录不存在，跳过清理")
        return

    keep = {f"{top}_语义.md" for top in tops} | {"概念.md", "实体.md"}
    legacy = sorted(
        path
        for path in semantic_dir.rglob("*.md")
        if path.is_file() and path.name.endswith("_语义.md") and path.name not in keep
    )
    print(f"待清理旧卡片 {len(legacy)} 个")
    if args.dry_run:
        for path in legacy:
            print(f"  [dry-run] 删除：{path.relative_to(workspace)}")
        return
    for path in legacy:
        path.unlink()
        print(f"  已删除：{path.relative_to(workspace)}")
    removed_dirs = 0
    for directory in sorted(semantic_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
            removed_dirs += 1
    print(f"已清理空目录 {removed_dirs} 个")

    links = sync_semantic_links(str(workspace))
    print(f"WIKI.md 联动：{links}")

    print(f"\n完成：语义卡片 {len(legacy) + len(tops)} 个 → {len(tops)} 个合并文件")


if __name__ == "__main__":
    main()
