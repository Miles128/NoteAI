import os
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from io import BytesIO

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import logger
from utils.helpers import get_file_extension, read_file_with_encoding


class FilePreviewer:
    SUPPORTED_PREVIEW_TYPES = ['.md', '.markdown', '.txt', '.pdf', '.doc', '.docx']

    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path

    def can_preview(self, file_path: str) -> bool:
        ext = get_file_extension(file_path).lower()
        return ext in self.SUPPORTED_PREVIEW_TYPES

    def get_preview_data(self, file_path: str) -> Dict[str, Any]:
        if not self.workspace_path:
            full_path = file_path
        else:
            full_path = os.path.join(self.workspace_path, file_path)

        if not os.path.exists(full_path):
            return {
                'success': False,
                'error': '文件不存在'
            }

        ext = get_file_extension(full_path).lower()
        file_size = os.path.getsize(full_path)

        try:
            if ext == '.md' or ext == '.markdown':
                return self._preview_markdown(full_path, file_size)
            elif ext == '.txt':
                return self._preview_text(full_path, file_size)
            elif ext == '.pdf':
                return self._preview_pdf(full_path, file_size)
            elif ext in ['.doc', '.docx']:
                return self._preview_word(full_path, file_size)
            else:
                return {
                    'success': False,
                    'error': f'不支持预览此文件类型: {ext}'
                }
        except Exception as e:
            logger.error(f"预览失败 {full_path}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _preview_markdown(self, file_path: str, file_size: int) -> Dict[str, Any]:
        content = read_file_with_encoding(file_path)
        content_hash = hash(content)

        return {
            'success': True,
            'type': 'markdown',
            'file_name': os.path.basename(file_path),
            'file_size': file_size,
            'content': content,
            'content_hash': content_hash
        }

    def _preview_text(self, file_path: str, file_size: int) -> Dict[str, Any]:
        content = read_file_with_encoding(file_path)
        content_hash = hash(content)

        return {
            'success': True,
            'type': 'text',
            'file_name': os.path.basename(file_path),
            'file_size': file_size,
            'content': content,
            'content_hash': content_hash
        }

    def _preview_pdf(self, file_path: str, file_size: int) -> Dict[str, Any]:
        try:
            import fitz
        except ImportError:
            return self._preview_pdf_legacy(file_path, file_size)

        pages_data = []
        total_pages = 0
        full_text = ""

        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)

            for page_num in range(total_pages):
                page = doc[page_num]

                text = page.get_text("text") or ""

                mat = fitz.Matrix(1.5, 1.5)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_bytes = pix.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")

                pages_data.append({
                    "page_number": page_num + 1,
                    "text": text,
                    "image": img_base64,
                    "width": pix.width,
                    "height": pix.height
                })

                full_text += text + "\n\n"

            doc.close()

            return {
                "success": True,
                "type": "pdf",
                "file_name": os.path.basename(file_path),
                "file_size": file_size,
                "total_pages": total_pages,
                "pages": pages_data,
                "full_text": full_text.strip()
            }
        except Exception as e:
            logger.error(f"PDF预览失败 (PyMuPDF): {e}")
            return self._preview_pdf_legacy(file_path, file_size)

    def _preview_pdf_legacy(self, file_path: str, file_size: int) -> Dict[str, Any]:
        import fitz

        pages_data = []
        total_pages = 0

        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            for i, page in enumerate(doc):
                text = page.get_text("text") or ""
                pages_data.append({
                    "page_number": i + 1,
                    "text": text.strip(),
                    "image": None,
                    "width": 0,
                    "height": 0
                })
            doc.close()

            return {
                "success": True,
                "type": "pdf",
                "file_name": os.path.basename(file_path),
                "file_size": file_size,
                "total_pages": total_pages,
                "pages": pages_data,
                "full_text": "\n\n".join([p["text"] for p in pages_data])
            }
        except Exception as e:
            logger.error(f"PDF预览失败 (legacy): {e}")
            return {
                "success": False,
                "error": f"PDF解析失败: {str(e)}"
            }

    def _preview_pdf(self, file_path: str, file_size: int) -> Dict[str, Any]:
        import fitz

        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            pages_data = []
            text_parts = []
            for i, page in enumerate(doc):
                text = page.get_text("text") or ""
                pages_data.append({
                    "page_number": i + 1,
                    "text": text.strip(),
                    "image": None,
                    "width": 0,
                    "height": 0
                })
                if text.strip():
                    text_parts.append(text.strip())
            doc.close()

            return {
                "success": True,
                "type": "pdf",
                "file_name": os.path.basename(file_path),
                "file_size": file_size,
                "total_pages": total_pages,
                "pages": pages_data,
                "full_text": "\n\n".join(text_parts)
            }
        except Exception as e:
            logger.error(f"PDF预览失败 (PyMuPDF): {e}")
            return self._preview_pdf_legacy(file_path, file_size)

    def _preview_word(self, file_path: str, file_size: int) -> Dict[str, Any]:
        from docx import Document
        from docx.shared import Pt
        import re

        try:
            doc = Document(file_path)
            paragraphs_data = []

            for i, para in enumerate(doc.paragraphs):
                text = para.text.strip()
                if text:
                    style_name = para.style.name if para.style else 'Normal'
                    paragraphs_data.append({
                        'index': i,
                        'text': text,
                        'style': style_name
                    })

            full_text = '\n'.join([p['text'] for p in paragraphs_data])

            tables_data = []
            for table_idx, table in enumerate(doc.tables):
                table_rows = []
                for row in table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells]
                    table_rows.append(row_cells)
                if table_rows:
                    tables_data.append({
                        'index': table_idx,
                        'rows': table_rows
                    })

            return {
                'success': True,
                'type': 'word',
                'file_name': os.path.basename(file_path),
                'file_size': file_size,
                'paragraphs': paragraphs_data,
                'tables': tables_data,
                'full_text': full_text
            }
        except Exception as e:
            logger.error(f"Word文档预览失败: {e}")
            return {
                'success': False,
                'error': f'Word文档解析失败: {str(e)}'
            }


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def get_file_type_display_name(ext: str) -> str:
    type_map = {
        '.md': 'Markdown',
        '.markdown': 'Markdown',
        '.txt': '文本文件',
        '.pdf': 'PDF文档',
        '.doc': 'Word文档',
        '.docx': 'Word文档'
    }
    return type_map.get(ext.lower(), '未知类型')
