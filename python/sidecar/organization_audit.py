"""High-confidence, non-destructive organization checks for Notes/."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from config.constants import TOPIC_SEP
from config.settings import NOTES_FOLDER
from sidecar.text_similarity import bounded as _bounded
from sidecar.text_similarity import jaccard as _jaccard
from sidecar.text_similarity import normalize_body as _normalize_body
from sidecar.text_similarity import shingles as _shingles
from sidecar.text_similarity import simhash as _simhash
from utils.text_utils import _is_generic_word, _is_meaningful_tag, parse_frontmatter, tokenize

NEAR_DUPLICATE_THRESHOLD = 0.78
_MIN_NEAR_DUPLICATE_CHARS = 120
_SIMHASH_MAX_DISTANCE = 12

MISPLACED_MIN_SCORE = 0.28
MISPLACED_MIN_GAP = 0.18
MISPLACED_SCORE_RATIO = 1.8
_MIN_TOPIC_NOTES = 2
_MAX_PROFILE_CHARS = 12000


@dataclass
class _NoteFeatures:
    path: Path
    rel: str
    topic: str
    normalized: str
    shingles: set[str]
    simhash: int
    terms: Counter[str]


def _iter_notes(root: Path) -> list[Path]:
    from utils.note_scanner import iter_note_files

    return sorted(
        iter_note_files(root),
        key=lambda path: str(path.relative_to(root)),
    )


def _topic_from_path(root: Path, note: Path) -> str:
    try:
        parts = note.relative_to(root / NOTES_FOLDER).parts[:-1]
    except ValueError:
        return ""
    return TOPIC_SEP.join(parts[:3]) if parts else ""


def _term_counter(title: str, tags: list[str], body: str) -> Counter[str]:
    sample = f"{title} {title} {' '.join(tags)} {_bounded(body, _MAX_PROFILE_CHARS)}"
    terms: Counter[str] = Counter()
    for raw in tokenize(sample):
        token = str(raw).strip().casefold()
        if not token or _is_generic_word(token) or not _is_meaningful_tag(token):
            continue
        terms[token] += 1
    return terms


def _load_features(root: Path) -> list[_NoteFeatures]:
    features: list[_NoteFeatures] = []
    for path in _iter_notes(root):
        try:
            meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        topic = _topic_from_path(root, path)
        if not topic and isinstance(meta, dict):
            raw_topic = meta.get("topic") or ""
            if isinstance(raw_topic, list):
                raw_topic = raw_topic[0] if raw_topic else ""
            topic = str(raw_topic).strip()
        raw_tags = meta.get("tags", []) if isinstance(meta, dict) else []
        if isinstance(raw_tags, str):
            tags = [raw_tags]
        elif isinstance(raw_tags, list):
            tags = [str(tag) for tag in raw_tags]
        else:
            tags = []
        normalized = _normalize_body(body)
        shingles = _shingles(normalized)
        features.append(
            _NoteFeatures(
                path=path,
                rel=str(path.relative_to(root)),
                topic=topic,
                normalized=normalized,
                shingles=shingles,
                simhash=_simhash(shingles),
                terms=_term_counter(path.stem, tags, body),
            )
        )
    return features


def _find_near_duplicates(notes: list[_NoteFeatures]) -> list[dict]:
    results: list[dict] = []
    for index, current in enumerate(notes):
        if len(current.normalized) < _MIN_NEAR_DUPLICATE_CHARS:
            continue
        best: tuple[_NoteFeatures, float] | None = None
        for candidate in notes[:index]:
            if len(candidate.normalized) < _MIN_NEAR_DUPLICATE_CHARS:
                continue
            if current.normalized == candidate.normalized:
                continue
            length_ratio = min(len(current.normalized), len(candidate.normalized)) / max(
                len(current.normalized), len(candidate.normalized)
            )
            if length_ratio < 0.65:
                continue
            if (current.simhash ^ candidate.simhash).bit_count() > _SIMHASH_MAX_DISTANCE:
                continue
            score = _jaccard(current.shingles, candidate.shingles)
            if score < NEAR_DUPLICATE_THRESHOLD:
                continue
            if best is None or score > best[1]:
                best = (candidate, score)
        if best:
            results.append(
                {
                    "file_path": current.rel,
                    "related_file": best[0].rel,
                    "score": round(best[1], 4),
                }
            )
    return results


def find_near_duplicates(root: Path) -> list[dict]:
    """Return the best earlier near-duplicate for each note."""
    return _find_near_duplicates(_load_features(root))


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = left.keys() & right.keys()
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _find_misplaced_notes(all_notes: list[_NoteFeatures]) -> list[dict]:
    notes = [note for note in all_notes if note.topic and note.terms]
    topic_profiles: dict[str, Counter[str]] = {}
    topic_counts: Counter[str] = Counter()
    for note in notes:
        topic_profiles.setdefault(note.topic, Counter()).update(note.terms)
        topic_counts[note.topic] += 1
    if len(topic_profiles) < 2:
        return []

    results: list[dict] = []
    for note in notes:
        if topic_counts[note.topic] < _MIN_TOPIC_NOTES:
            continue
        current_profile = topic_profiles[note.topic].copy()
        current_profile.subtract(note.terms)
        current_profile += Counter()
        current_score = _cosine(note.terms, current_profile)

        best_topic = ""
        best_score = 0.0
        for topic, profile in topic_profiles.items():
            if topic == note.topic or topic_counts[topic] < _MIN_TOPIC_NOTES:
                continue
            score = _cosine(note.terms, profile)
            if score > best_score:
                best_topic = topic
                best_score = score

        if not best_topic or best_score < MISPLACED_MIN_SCORE:
            continue
        if best_score - current_score < MISPLACED_MIN_GAP:
            continue
        if best_score < max(current_score * MISPLACED_SCORE_RATIO, MISPLACED_MIN_SCORE):
            continue
        results.append(
            {
                "file_path": note.rel,
                "current_topic": note.topic,
                "suggested_topic": best_topic,
                "current_score": round(current_score, 4),
                "suggested_score": round(best_score, 4),
            }
        )
    return results


def find_misplaced_notes(root: Path) -> list[dict]:
    """Flag notes whose content profile strongly favors another established topic."""
    from sidecar.topic_placement import is_placement_kept

    return [
        item
        for item in _find_misplaced_notes(_load_features(root))
        if not is_placement_kept(
            root,
            item["file_path"],
            item["current_topic"],
            item["suggested_topic"],
        )
    ]


def run_organization_audit(root: Path) -> dict[str, list[dict]]:
    """Run both organization checks from one bounded read/tokenization pass."""
    notes = _load_features(root)
    from sidecar.topic_placement import is_placement_kept

    misplaced = [
        item
        for item in _find_misplaced_notes(notes)
        if not is_placement_kept(
            root,
            item["file_path"],
            item["current_topic"],
            item["suggested_topic"],
        )
    ]
    return {
        "near_duplicates": _find_near_duplicates(notes),
        "misplaced_notes": misplaced,
    }
