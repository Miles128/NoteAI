"""Lightweight in-memory inverted index for full-text search across workspace .md files.

Avoids scanning every file on every query — builds a word→(file→positions) map
and re-indexes when workspace files change.
"""

import re
import threading
from pathlib import Path

from config import config

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


class FullTextIndex:
    """Inverted index: word → {file_relpath: [position, ...]}"""

    __slots__ = ("_index", "_files", "_lock", "_dirty")

    def __init__(self):
        self._index: dict[str, dict[str, list[int]]] = {}
        self._files: dict[str, float] = {}  # relpath → mtime
        self._lock = threading.Lock()
        self._dirty = True

    def ensure_indexed(self) -> bool:
        """Rebuild index if workspace files have changed.  Returns True if rebuilt."""
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
                words = _WORD_RE.findall(text.lower())
                for pos, word in enumerate(words):
                    self._index.setdefault(word, {}).setdefault(rel, []).append(pos)

            self._dirty = False
            return True

    def search(self, query: str, max_results: int = 50) -> list:
        """Return list of (relpath, score, snippet) sorted by relevance."""
        query_words = [w.lower() for w in _WORD_RE.findall(query)]
        if not query_words:
            return []

        self.ensure_indexed()

        with self._lock:
            file_hits: dict[str, int] = {}
            for word in query_words:
                for rel in self._index.get(word, {}):
                    file_hits[rel] = file_hits.get(rel, 0) + len(self._index[word][rel])

            scored = sorted(file_hits.items(), key=lambda x: -x[1])[:max_results]

        results = []
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

    def clear(self) -> None:
        with self._lock:
            self._index.clear()
            self._files.clear()
            self._dirty = True


# Shared singleton (replaces scanning every file on each request).
fulltext_index = FullTextIndex()
