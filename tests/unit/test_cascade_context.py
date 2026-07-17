from __future__ import annotations

from sidecar.cascade import _clamp_context, compress_notes_if_needed


def test_compress_notes_enforces_total_character_budget() -> None:
    notes = [
        {"file_name": f"{index}.md", "file_path": f"Notes/{index}.md", "content": "知识内容。" * 1000}
        for index in range(8)
    ]

    compressed = compress_notes_if_needed(notes, max_total_len=5000)

    assert len(compressed) == len(notes)
    assert sum(len(note["content"]) for note in compressed) <= 5000
    assert all(note["file_name"] for note in compressed)


def test_clamp_context_preserves_head_and_tail_within_budget() -> None:
    text = "开头" + ("中间" * 1000) + "结尾"

    result = _clamp_context(text, 500)

    assert len(result) <= 500
    assert result.startswith("开头")
    assert result.endswith("结尾")
    assert "内容已压缩" in result
