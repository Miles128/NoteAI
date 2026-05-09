"""PDF 文本提取工具"""

from typing import List


def extract_pdf_text(file_path: str, strip: bool = True) -> str:
    """
    使用 PyMuPDF（fitz）从 PDF 文件中提取全部文本，并以页为单位用双换行拼接。

    Args:
        file_path: PDF 文件路径
        strip: 是否对每页文本执行 strip()，默认 True

    Returns:
        所有页面文本拼接后的字符串
    """
    import fitz

    doc = fitz.open(file_path)
    parts = []
    for page in doc:
        text = page.get_text("text")
        parts.append(text.strip() if strip else text)
    doc.close()
    return "\n\n".join(parts)


def extract_pdf_pages(file_path: str) -> List[str]:
    """
    使用 PyMuPDF（fitz）从 PDF 文件中逐页提取文本。

    Args:
        file_path: PDF 文件路径

    Returns:
        每页文本的列表，顺序与页码一致，每条文本已 strip()
    """
    import fitz

    doc = fitz.open(file_path)
    texts = [page.get_text("text").strip() for page in doc]
    doc.close()
    return texts
