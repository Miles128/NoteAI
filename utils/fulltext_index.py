"""Lightweight in-memory inverted index for full-text search across workspace .md files.

Avoids scanning every file on every query — builds a term→(file→positions) map
and re-indexes when workspace files change.

中文按「相邻二字组合」（bigram）入索引：连续的汉字会被整块切成一个 token，
按整块精确匹配的话搜「笔记」命中不了「我的笔记系统」；查询侧同样切成 bigram
并要求同组全部命中，等价于子串包含匹配。
"""

import re
import threading
from pathlib import Path

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


_CJK_RUN_RE = re.compile(r"([一-鿿]+)")
_CJK_FULL_RE = re.compile(r"[一-鿿]+")
_LATIN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _term_groups(text: str) -> list[list[str]]:
    """切成检索单元组；同组内的项必须同时出现。

    中文串 → 相邻二字组合（单字串即其本身）；拉丁/数字片段 → 原样一个单元。
    """
    groups: list[list[str]] = []
    for token in _WORD_RE.findall(text.lower()):
        for run in _CJK_RUN_RE.split(token):
            if not run:
                continue
            if _CJK_FULL_RE.fullmatch(run):
                if len(run) == 1:
                    groups.append([run])
                else:
                    groups.append(sorted({run[i : i + 2] for i in range(len(run) - 1)}))
            else:
                groups.extend([frag] for frag in _LATIN_RE.findall(run))
    return groups


class FullTextIndex:
    """Inverted index: term → {file_relpath: [position, ...]}"""

    __slots__ = ("_index", "_files", "_lock", "_dirty")

    def __init__(self):
        self._index: dict[str, dict[str, list[int]]] = {}
        self._files: dict[str, float] = {}  # relpath → mtime
        self._lock = threading.Lock()
        self._dirty = True

    def ensure_indexed(self) -> bool:
        """Rebuild index if workspace files have changed.  Returns True if rebuilt."""
        from config import config

        workspace = config.workspace_path
        if not workspace:
            return False

        with self._lock:
            if not self._dirty and not self._index:
                self._dirty = True

            if not self._dirty:
                return False

            self._index.clear()
            was_dirty = self._dirty
            old_files = dict(self._files)
            self._files.clear()
            self._dirty = False

            ws = Path(workspace)
            for md_file in ws.rglob("*.md"):
                if md_file.name.startswith("."):
                    continue
                if "wiki" in {p.lower() for p in md_file.relative_to(ws).parts}:
                    continue
                rel = str(md_file.relative_to(ws))
                try:
                    mtime = md_file.stat().st_mtime
                except OSError:
                    continue
                self._files[rel] = mtime
                if not was_dirty and rel in old_files and old_files[rel] == mtime:
                    continue
                try:
                    text = md_file.read_text(encoding="utf-8")
                except Exception:
                    continue
                for pos, group in enumerate(_term_groups(text)):
                    for term in group:
                        self._index.setdefault(term, {}).setdefault(rel, []).append(pos)

            self._dirty = False
            return True

    def search(self, query: str, max_results: int = 50) -> list:
        """Return list of (relpath, score, snippet) sorted by relevance."""
        groups = _term_groups(query)
        if not groups:
            return []

        self.ensure_indexed()

        with self._lock:
            # 组间 AND、组内 AND：每个检索单元组都必须在同一文件里命中，
            # 文件得分取各组命中次数（组内按最少那次计，避免重复字膨胀）。
            file_hits: dict[str, int] | None = None
            for group in groups:
                clause: dict[str, int] | None = None
                for term in group:
                    postings = self._index.get(term)
                    if not postings:
                        clause = {}
                        break
                    counts = {rel: len(positions) for rel, positions in postings.items()}
                    if clause is None:
                        clause = counts
                    else:
                        clause = {rel: min(n, clause[rel]) for rel, n in counts.items() if rel in clause}
                if not clause:
                    return []
                if file_hits is None:
                    file_hits = clause
                else:
                    file_hits = {rel: n + file_hits[rel] for rel, n in clause.items() if rel in file_hits}
                    if not file_hits:
                        return []

            scored = sorted((file_hits or {}).items(), key=lambda x: -x[1])[:max_results]

        results: list[dict[str, str | int]] = []
        from config import config

        workspace = config.workspace_path
        if not workspace:
            return results

        for rel, score in scored:
            fpath = Path(workspace) / rel
            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue
            snippet = text[:300].replace("\n", " ")
            if len(text) > 300:
                snippet += "..."
            results.append({"path": rel, "score": score, "snippet": snippet})

        return results

    def mark_dirty(self) -> None:
        """Signal that the index is stale (called on file change)."""
        with self._lock:
            self._dirty = True

    def stats(self) -> dict[str, int]:
        """Indexed file / term counts, for health reporting."""
        with self._lock:
            return {"files": len(self._files), "terms": len(self._index)}

    def clear(self) -> None:
        with self._lock:
            self._index.clear()
            self._files.clear()
            self._dirty = True


# Shared singleton (replaces scanning every file on each request).
fulltext_index = FullTextIndex()
