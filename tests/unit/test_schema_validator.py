import pytest

from sidecar.schema_validator import (
    check_notes_writable,
    check_wiki_writable,
    require_topic,
    topic_depth,
    validate_topic,
)


def test_validate_topic_depth() -> None:
    ok, _ = validate_topic("A > B > C > D", {"max_topic_depth": 3})
    assert ok is False
    ok, _ = validate_topic("A > B > C", {"max_topic_depth": 3})
    assert ok is True


def test_validate_topic_forbidden_leaf() -> None:
    ok, msg = validate_topic("AI > 其他")
    assert ok is False
    assert "其他" in msg


def test_topic_depth() -> None:
    assert topic_depth("A > B") == 2


def test_check_wiki_writable_respects_schema(tmp_path, monkeypatch) -> None:
    from config import config

    ws = tmp_path / "w"
    ws.mkdir()
    (ws / "schema.md").write_text(
        "ai_may_edit_wiki: false\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "workspace_path", str(ws))
    ok, msg = check_wiki_writable("测试")
    assert ok is False
    assert "wiki" in msg


def test_check_notes_writable_default_denied(tmp_path, monkeypatch) -> None:
    from config import config

    ws = tmp_path / "w"
    ws.mkdir()
    (ws / "schema.md").write_text(
        "ai_may_edit_notes: false\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "workspace_path", str(ws))
    ok, _ = check_notes_writable()
    assert ok is False


def test_require_topic_combined(tmp_path, monkeypatch) -> None:
    from config import config

    ws = tmp_path / "w"
    ws.mkdir()
    monkeypatch.setattr(config, "workspace_path", str(ws))
    ok, _ = require_topic("合法 > 主题")
    assert ok is False
