from __future__ import annotations

from pathlib import Path
from threading import Barrier, Thread

from modules.file_converter import FileConverterManager, LegacyPPTConverter


def _ppt_record(record_type: int, payload: bytes) -> bytes:
    return b"\x00\x00" + record_type.to_bytes(2, "little") + len(payload).to_bytes(4, "little") + payload


def test_supported_formats_include_legacy_office() -> None:
    formats = set(FileConverterManager.get_supported_formats())

    assert ".doc" in formats
    assert ".ppt" in formats


def test_legacy_ppt_text_record_extraction() -> None:
    converter = LegacyPPTConverter()
    data = b"".join(
        [
            _ppt_record(converter.TEXT_CHARS_ATOM, "标题".encode("utf-16le")),
            _ppt_record(converter.TEXT_BYTES_ATOM, b"ASCII body"),
            _ppt_record(converter.CSTRING, "备注".encode("utf-16le")),
        ]
    )

    texts = converter._extract_text_records(data)

    assert texts == ["标题", "ASCII body", "备注"]


def test_convert_file_returns_path_after_topic_assignment(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.txt"
    source.write_text("input", encoding="utf-8")
    output_dir = tmp_path / "Notes"
    assigned = output_dir / "技术" / "source.md"

    class Converter:
        def to_markdown(self, _path: str) -> str:
            return "# 标题\n\n这是一段足够完整的转换内容，包含标点，也包含多个句子。用于验证最终文件路径。"

    def assign(path: str) -> dict:
        assigned.parent.mkdir(parents=True)
        Path(path).rename(assigned)
        return {
            "status": "auto_assigned",
            "new_path": "Notes/技术/source.md",
            "file_path": str(assigned),
        }

    manager = FileConverterManager()
    monkeypatch.setattr(manager, "_get_converter", lambda _ext: Converter())
    monkeypatch.setattr("utils.topic_assigner.auto_assign_topic_for_file", assign)

    result = manager.convert_file(str(source), str(output_dir))

    assert result["success"] is True
    assert result["output_path"] == str(assigned)
    assert assigned.is_file()


def test_parallel_conversions_do_not_overwrite_same_output(tmp_path: Path, monkeypatch) -> None:
    sources = [tmp_path / "a" / "same.txt", tmp_path / "b" / "same.txt"]
    for source in sources:
        source.parent.mkdir()
        source.write_text("input", encoding="utf-8")
    output_dir = tmp_path / "Notes"
    barrier = Barrier(2)
    results: list[dict] = []

    class Converter:
        def to_markdown(self, path: str) -> str:
            barrier.wait()
            return f"# 标题\n\n{path} 的完整转换内容，包含足够的标点和句子。"

    monkeypatch.setattr(FileConverterManager, "_get_converter", lambda _self, _ext: Converter())
    monkeypatch.setattr("utils.topic_assigner.auto_assign_topic_for_file", lambda _path: None)

    threads = [
        Thread(
            target=lambda source=source: results.append(
                FileConverterManager().convert_file(str(source), str(output_dir))
            )
        )
        for source in sources
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    output_paths = {result["output_path"] for result in results}
    assert output_paths == {str(output_dir / "same.md"), str(output_dir / "same_1.md")}
    assert all(Path(path).is_file() for path in output_paths)


def test_move_to_raw_keeps_file_already_in_raw(tmp_path: Path) -> None:
    raw_dir = tmp_path / "Raw"
    source = raw_dir / "archive.pdf"
    source.parent.mkdir()
    source.write_bytes(b"pdf")

    moved = FileConverterManager()._move_to_raw(str(source), str(raw_dir))

    assert moved is True
    assert source.is_file()
    assert list(raw_dir.iterdir()) == [source]


def test_convert_can_defer_topic_assignment_for_ingest(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.txt"
    source.write_text("input", encoding="utf-8")
    assignment_calls: list[str] = []

    class Converter:
        def to_markdown(self, _path: str) -> str:
            return "# 标题\n\n这是编译前的转换内容，包含足够的信息和完整的句子，用于验证延后主题分配。"

    manager = FileConverterManager()
    monkeypatch.setattr(manager, "_get_converter", lambda _ext: Converter())
    monkeypatch.setattr(
        "utils.topic_assigner.auto_assign_topic_for_file",
        lambda path: assignment_calls.append(path),
    )

    result = manager.convert_file(str(source), str(tmp_path / "Notes"), assign_topic=False)

    assert result["success"] is True
    assert assignment_calls == []


def test_low_quality_scanned_pdf_is_rejected(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"pdf")

    class Converter:
        def to_markdown(self, _path: str) -> str:
            return ""

    manager = FileConverterManager()
    monkeypatch.setattr(manager, "_get_converter", lambda _ext: Converter())

    result = manager.convert_file(str(source), str(tmp_path / "Notes"), assign_topic=False)

    assert result["success"] is False
    assert result["quality"]["suspected_scanned_pdf"] is True
    assert "无法可靠提取正文" in result["error"]
    assert not list((tmp_path / "Notes").glob("*.md")) if (tmp_path / "Notes").exists() else True


def test_same_source_hash_is_converted_once_and_archived(tmp_path: Path, monkeypatch) -> None:
    raw_dir = tmp_path / "Raw"
    raw_dir.mkdir()
    source = raw_dir / "source.txt"
    source.write_text("same source", encoding="utf-8")

    class Converter:
        def to_markdown(self, _path: str) -> str:
            return "# 标题\n\n这是足够完整的转换内容，包含多个句子和必要的信息，可以安全进入知识库。"

    manager = FileConverterManager()
    monkeypatch.setattr(manager, "_get_converter", lambda _ext: Converter())

    first = manager.convert_file(str(source), str(tmp_path / "Notes"), assign_topic=False, raw_path=str(raw_dir))
    second = manager.convert_file(str(source), str(tmp_path / "Notes"), assign_topic=False, raw_path=str(raw_dir))

    assert first["success"] is True
    assert second["success"] is True
    assert second["skipped"] is True
    assert first["output_path"] == second["output_path"]
    assert len(list((tmp_path / "Notes").glob("*.md"))) == 1
