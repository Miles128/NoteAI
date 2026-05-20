from __future__ import annotations

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
