from pathlib import Path

import yaml

from sidecar.rag.question_shape import (
    SHAPE_COMPARE,
    SHAPE_DEFAULT,
    SHAPE_DEFINE,
    SHAPE_GAP,
    SHAPE_TEACH,
    classify_question_shape,
    prompt_key_for_shape,
)

GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "rag_gold_questions.yaml"


def test_compare_wins_over_define():
    assert classify_question_shape("RAG 和 Fine-tune 的区别是什么") == SHAPE_COMPARE


def test_gap_before_define():
    assert classify_question_shape("这个主题还缺什么") == SHAPE_GAP


def test_empty_is_default():
    assert classify_question_shape("") == SHAPE_DEFAULT
    assert classify_question_shape("   ") == SHAPE_DEFAULT


def test_prompt_key_mapping():
    assert prompt_key_for_shape(SHAPE_TEACH) == "RAG_CHAT_SHAPE_TEACH"
    assert prompt_key_for_shape("unknown") == "RAG_CHAT_SHAPE_DEFAULT"


def test_gold_question_shapes():
    rows = yaml.safe_load(GOLD.read_text(encoding="utf-8"))
    assert len(rows) >= 20
    mismatches = []
    for row in rows:
        got = classify_question_shape(row["q"])
        if got != row["shape"]:
            mismatches.append(f"{row['q']!r}: expected {row['shape']}, got {got}")
    assert not mismatches, "\n".join(mismatches)
