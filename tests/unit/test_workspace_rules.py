from pathlib import Path

import pytest

from config import config
from config.settings import WORKSPACE_APP_FOLDER
from sidecar.workspace_rules import (
    RULES_FILENAME,
    format_wiki_topic_structure_for_llm,
    get_workspace_rules_options,
    load_workspace_rules,
    needs_workspace_rules_setup,
    resolve_survey_topic,
    save_workspace_rules_options,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir()
    (d / "Notes").mkdir()
    config.workspace_path = str(d)
    return d


def _write_rules(workspace: Path, **overrides) -> None:
    base = {
        "max_topic_depth": 3,
        "auto_update_survey": True,
        "survey_at_level": 2,
        "ai_may_edit_wiki": True,
        "ai_may_edit_notes": False,
        "configured": True,
    }
    base.update(overrides)
    path = workspace / WORKSPACE_APP_FOLDER / RULES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")


def test_needs_setup_when_unconfigured(workspace: Path) -> None:
    assert needs_workspace_rules_setup(str(workspace)) is True


def test_save_options_marks_configured(workspace: Path) -> None:
    ok = save_workspace_rules_options({"max_topic_depth": 2, "auto_update_survey": False, "survey_at_level": 1})
    assert ok is True
    assert needs_workspace_rules_setup(str(workspace)) is False
    rules = load_workspace_rules(str(workspace))
    assert rules["max_topic_depth"] == 2
    assert rules["auto_update_survey"] is False


def test_l1_topics_from_wiki(workspace: Path) -> None:
    wiki = workspace / "wiki"
    wiki.mkdir()
    (wiki / "WIKI.md").write_text("## AI Agent\n\n## RAG\n", encoding="utf-8")
    opts = get_workspace_rules_options(str(workspace))
    assert opts["l1_topics"] == ["AI Agent", "RAG"]


def test_wiki_topic_structure_snippet(workspace: Path) -> None:
    wiki = workspace / "wiki"
    wiki.mkdir()
    (wiki / "WIKI.md").write_text("## AI Agent\n### 记忆\n", encoding="utf-8")
    text = format_wiki_topic_structure_for_llm(workspace=str(workspace))
    assert "AI Agent" in text
    assert "记忆" in text


def test_resolve_survey_topic() -> None:
    assert resolve_survey_topic("AI Agent > 记忆", 1) == "AI Agent"
    assert resolve_survey_topic("AI Agent > 记忆", 2) == "AI Agent > 记忆"


def test_migrate_from_legacy_schema(workspace: Path) -> None:
    (workspace / "schema.md").write_text(
        "max_topic_depth: 2\nauto_update_survey: false\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    rules = load_workspace_rules(str(workspace))
    assert rules["max_topic_depth"] == 2
    assert rules["auto_update_survey"] is False
    assert (workspace / WORKSPACE_APP_FOLDER / RULES_FILENAME).exists()
