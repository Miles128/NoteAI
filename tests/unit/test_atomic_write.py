"""Tests for utils.atomic_write."""

from __future__ import annotations

import os
from pathlib import Path

from utils.atomic_write import atomic_write_text


def test_atomic_write_text_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    out = atomic_write_text(target, "# hi\n\nbody\n")
    assert out == target
    assert target.read_text(encoding="utf-8") == "# hi\n\nbody\n"
    # no temp leftovers
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_mkdir_parents(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "dir" / "note.md"
    atomic_write_text(target, "x", mkdir_parents=True)
    assert target.read_text(encoding="utf-8") == "x"


def test_atomic_write_text_cleans_temp_on_failure(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "note.md"
    real_replace = os.replace

    def _boom(*args, **kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(os, "replace", _boom)
    try:
        atomic_write_text(target, "x")
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError")
    assert not target.exists()
    assert list(tmp_path.glob("*.tmp")) == []
    monkeypatch.setattr(os, "replace", real_replace)
