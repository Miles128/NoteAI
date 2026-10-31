import base64
import os
from typing import Any

from utils.helpers import get_file_extension, read_file_with_encoding
from utils.logger import logger


class FilePreviewer:
    SUPPORTED_PREVIEW_TYPES = [".md", ".markdown", ".txt", ".doc", ".docx"]

    def __init__(self, workspace_path: str | None = None):
        self.workspace_path = workspace_path

    def can_preview(self, file_path: str) -> bool:
        ext = get_file_extension(file_path).lower()
        return ext in self.SUPPORTED_PREVIEW_TYPES

    def get_preview_data(self, file_path: str) -> dict[str, Any]:
        full_path = file_path
        if not os.path.isabs(full_path) and self.workspace_path:
            full_path = os.path.join(self.workspace_path, file_path)

        if not os.path.exists(full_path):
            return {"success": False, "error": "文件不存在"}

        ext = get_file_extension(full_path).lower()
        file_size = os.path.getsize(full_path)

        try:
            if ext == ".md" or ext == ".markdown":
                return self._preview_markdown(full_path, file_size)
            if ext == ".txt":
                return self._preview_text(full_path, file_size)
            if ext == ".docx":
                return self._preview_docx(full_path, file_size)
            if ext == ".doc":
                return self._preview_doc_legacy(full_path, file_size)
            return {"success": False, "error": f"不支持预览此文件类型: {ext}"}
        except Exception as e:
            logger.error(f"预览失败 {full_path}: {e}")
            return {"success": False, "error": str(e)}

    def _utf8_transport(self, content: str) -> dict[str, Any]:
        """Encode preview text once as standard base64 (ASCII-safe over JSON-RPC)."""
        raw = content.encode("utf-8")
        return {
            "transport": "base64_utf8",
            "content_b64": base64.standard_b64encode(raw).decode("ascii"),
            "content_byte_length": len(raw),
        }

    def _preview_markdown(self, file_path: str, file_size: int) -> dict[str, Any]:
        content = read_file_with_encoding(file_path)

        return {
            "success": True,
            "type": "markdown",
            "preview_delivery": "semantic_b64",
            "file_name": os.path.basename(file_path),
            "file_size": file_size,
            **self._utf8_transport(content),
        }

    def _preview_text(self, file_path: str, file_size: int) -> dict[str, Any]:
        content = read_file_with_encoding(file_path)

        return {
            "success": True,
            "type": "text",
            "preview_delivery": "semantic_b64",
            "file_name": os.path.basename(file_path),
            "file_size": file_size,
            **self._utf8_transport(content),
        }

    def _preview_docx(self, file_path: str, file_size: int) -> dict[str, Any]:
        """DOCX → HTML（mammoth），供前端排版预览。"""
        try:
            import mammoth
        except ImportError:
            return self._preview_docx_python_docx(file_path, file_size)

        try:
            with open(file_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
            html = (result.value or "").strip()
            if not html:
                return self._preview_docx_python_docx(file_path, file_size)

            payload: dict[str, Any] = {
                "success": True,
                "type": "docx",
                "content_kind": "html",
                "preview_delivery": "semantic_b64",
                "file_name": os.path.basename(file_path),
                "file_size": file_size,
                **self._utf8_transport(html),
            }
            messages = [str(m) for m in getattr(result, "messages", [])]
            if messages:
                payload["warnings"] = messages[:8]
            return payload
        except Exception as e:
            logger.warning(f"DOCX mammoth 预览失败，回退 python-docx: {e}")
            return self._preview_docx_python_docx(file_path, file_size)

    def _preview_docx_python_docx(self, file_path: str, file_size: int) -> dict[str, Any]:
        from docx import Document

        try:
            doc = Document(file_path)
            parts: list[str] = []
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                style_name = (para.style.name if para.style else "Normal") or "Normal"
                if style_name.startswith("Heading"):
                    level = "".join(c for c in style_name if c.isdigit()) or "1"
                    parts.append(f"<h{level}>{self._escape_html(text)}</h{level}>")
                else:
                    parts.append(f"<p>{self._escape_html(text)}</p>")

            for table in doc.tables:
                rows_html: list[str] = []
                for row in table.rows:
                    cells = "".join(f"<td>{self._escape_html(cell.text.strip())}</td>" for cell in row.cells)
                    rows_html.append(f"<tr>{cells}</tr>")
                if rows_html:
                    parts.append("<table>" + "".join(rows_html) + "</table>")

            html = "".join(parts) or "<p>（文档无可见正文）</p>"
            return {
                "success": True,
                "type": "docx",
                "content_kind": "html",
                "preview_delivery": "semantic_b64",
                "file_name": os.path.basename(file_path),
                "file_size": file_size,
                **self._utf8_transport(html),
            }
        except Exception as e:
            logger.error(f"DOCX 预览失败: {e}")
            return {
                "success": False,
                "error": f"Word 文档解析失败: {str(e)}",
            }

    def _preview_doc_legacy(self, file_path: str, file_size: int) -> dict[str, Any]:
        """旧版 .doc：提取为 Markdown 后预览。"""
        try:
            from modules.file_converter import LegacyDOCConverter

            markdown_content = LegacyDOCConverter().to_markdown(file_path)
            return {
                "success": True,
                "type": "docx",
                "content_kind": "markdown",
                "preview_delivery": "semantic_b64",
                "file_name": os.path.basename(file_path),
                "file_size": file_size,
                **self._utf8_transport(markdown_content or ""),
            }
        except Exception as e:
            logger.error(f"DOC 预览失败: {e}")
            return {
                "success": False,
                "error": f"Word 文档解析失败: {str(e)}",
            }

    @staticmethod
    def _escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def get_file_type_display_name(ext: str) -> str:
    type_map = {
        ".md": "Markdown",
        ".markdown": "Markdown",
        ".txt": "文本文件",
        ".doc": "Word文档",
        ".docx": "Word文档",
    }
    return type_map.get(ext.lower(), "未知类型")
