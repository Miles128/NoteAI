"""Tests for utils.atomic_write."""

from __future__ import annotations

import os
import stat
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


def test_atomic_write_text_keeps_original_when_replace_fails(tmp_path: Path, monkeypatch) -> None:
    """崩溃/失败时旧内容必须完好——这是「不会留下半截笔记」的核心保证。"""
    target = tmp_path / "note.md"
    target.write_text("old body", encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(os, "replace", _boom)
    try:
        atomic_write_text(target, "new body")
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError")
    assert target.read_text(encoding="utf-8") == "old body"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_preserves_existing_mode(tmp_path: Path) -> None:
    """覆盖已有文件时必须继承原权限位（mkstemp 默认 0600 会把 0644 笔记悄悄改权限）。"""
    target = tmp_path / "note.md"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o644)

    atomic_write_text(target, "new")

    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_text_explicit_mode_wins(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o644)

    atomic_write_text(target, "new", mode=0o600)

    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_atomic_write_text_new_file_is_owner_only(tmp_path: Path) -> None:
    target = tmp_path / "fresh.md"
    atomic_write_text(target, "x")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
