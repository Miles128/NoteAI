from sidecar.archive_wiki import archive_chat_answer, parse_save_suggestion


def test_parse_save_suggestion_yes():
    text = "这是整合后的洞见。\n【存档建议】是"
    clean, suggest = parse_save_suggestion(text)
    assert suggest is True
    assert "存档建议" not in clean
    assert "洞见" in clean


def test_parse_save_suggestion_no():
    text = "根据笔记复述。\n【存档建议】否"
    clean, suggest = parse_save_suggestion(text)
    assert suggest is False
    assert "存档建议" not in clean


def test_parse_save_suggestion_missing_marker():
    clean, suggest = parse_save_suggestion("仅普通回答")
    assert suggest is False
    assert clean == "仅普通回答"
