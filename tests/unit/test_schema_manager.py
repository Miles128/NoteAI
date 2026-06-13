from pathlib import Path

import pytest
from sidecar.schema_manager import (
    DEFAULT_SCHEMA,
    SCHEMA_CONFIGURED_MARKER,
    SCHEMA_FILENAME,
    ensure_schema,
    finalize_schema_content,
    load_schema_text,
    needs_schema_setup,
    parse_schema_rules,
    save_schema_text,
)

from config import config


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir()
    (d / "Notes").mkdir()
    config.workspace_path = str(d)
    return d


def test_needs_setup_when_schema_missing(workspace: Path) -> None:
    assert needs_schema_setup(str(workspace)) is True
    path = ensure_schema()
    assert path is not None
    assert path.name == SCHEMA_FILENAME
    # Wizard creates schema; ensure_schema alone does not
    assert not path.exists()


def test_finalize_schema_marks_configured() -> None:
    body = finalize_schema_content("# test\n")
    assert SCHEMA_CONFIGURED_MARKER in body


def test_parse_schema_rules_defaults() -> None:
    rules = parse_schema_rules(DEFAULT_SCHEMA)
    assert rules["ai_may_edit_wiki"] is True
    assert rules["ai_may_edit_notes"] is False
    assert rules["max_topic_depth"] == 3


def test_migrate_legacy_schema_filename(workspace: Path) -> None:
    from sidecar.schema_manager import SCHEMA_VERSION_MARKER

    legacy = workspace / "SCHEMA.md"
    legacy.write_text(f"# kept\n<!-- {SCHEMA_VERSION_MARKER} -->\n", encoding="utf-8")
    path = ensure_schema()
    assert path is not None
    assert path.name == "schema.md"
    assert "# kept" in path.read_text(encoding="utf-8")


def test_save_and_load_schema(workspace: Path) -> None:
    ensure_schema()
    save_schema_text("# Custom\n\nai_may_edit_wiki: false\n")
    text = load_schema_text()
    assert "Custom" in text
    rules = parse_schema_rules(text)
    assert rules["ai_may_edit_wiki"] is False
