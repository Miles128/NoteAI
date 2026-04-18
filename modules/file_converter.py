import os
import re
from typing import Optional, Callable, Dict, List
from pathlib import Path
from abc import ABC, abstractmethod

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import config, RAW_FOLDER
from utils.logger import logger
from utils.helpers import (
    sanitize_filename, clean_text, remove_images_from_markdown,
    ensure_dir, get_file_extension, read_file_with_encoding,
    check_api_config, APIConfigError, NetworkError, is_network_error,
    clean_markdown_content, optimize_markdown_format,
    extract_pdf_text, extract_pdf_pages
)

class BaseConverter(ABC):
    """转换器基类"""

    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback

    @abstractmethod
    def to_markdown(self, file_path: str, ai_assist: bool = False) -> str:
        """转换为Markdown"""
        pass


class PDFConverter(BaseConverter):
    """PDF转Markdown转换器（仅使用快速路径）"""

    SUPPORTED_FORMATS = ['.pdf']

    MIN_PAGE_COUNT_FOR_SIGNATURE_DETECTION = 3
    SIGNATURE_MIN_LENGTH = 5
    SIGNATURE_MAX_LENGTH = 200
    SIGNATURE_MAX_LINES = 5

    def to_markdown(self, file_path: str, ai_assist: bool = True) -> str:
        """使用快速路径将PDF转换为Markdown（默认启用Python优化）"""
        logger.info(f"开始转换PDF: {file_path} (Python优化: {ai_assist})")

        try:
            markdown_content = self._extract_pdf_text(file_path)
            markdown_content = clean_text(markdown_content)
            markdown_content = self._remove_repeated_signatures(markdown_content, file_path)

            if ai_assist:
                logger.info("使用Python进行PDF内容优化...")
                markdown_content = clean_markdown_content(markdown_content)
                markdown_content = optimize_markdown_format(markdown_content)

            markdown_content = remove_images_from_markdown(markdown_content)

            logger.info(f"PDF转换完成: {file_path}")
            return markdown_content

        except Exception as e:
            logger.error(f"PDF转换失败 {file_path}: {e}")
            raise

    def _extract_pdf_text(self, file_path: str) -> str:
        """使用 PyMuPDF 提取 PDF 文本（统一入口）"""
        return extract_pdf_text(file_path)

    def _extract_page_texts(self, file_path: str) -> List[str]:
        """提取每一页的文本用于签名检测"""
        return extract_pdf_pages(file_path)

    def _find_signature_lines(self, page_texts: List[str]) -> set:
        """
        识别在每一页都出现的重复文本行（签名、页眉、页脚等）

        Returns:
            包含重复文本的集合
        """
        if len(page_texts) < self.MIN_PAGE_COUNT_FOR_SIGNATURE_DETECTION:
            return set()

        signature_candidates = []
        for page_text in page_texts:
            lines = page_text.split('\n')
            lines = [line.strip() for line in lines if line.strip()]
            signature_candidates.append(set(lines))

        common_lines = signature_candidates[0]
        for candidate_set in signature_candidates[1:]:
            common_lines &= candidate_set

        valid_signatures = set()
        for line in common_lines:
            if self.SIGNATURE_MIN_LENGTH <= len(line) <= self.SIGNATURE_MAX_LENGTH:
                valid_signatures.add(line)

        logger.info(f"检测到 {len(valid_signatures)} 条重复签名/页眉/页脚")
        return valid_signatures

    def _remove_repeated_signatures(self, markdown_content: str, file_path: str) -> str:
        """从Markdown内容中移除重复出现的签名、页眉、页脚"""
        import fitz

        doc = fitz.open(file_path)
        page_count = len(doc)
        doc.close()

        if page_count < self.MIN_PAGE_COUNT_FOR_SIGNATURE_DETECTION:
            logger.info(f"页数({page_count})少于{self.MIN_PAGE_COUNT_FOR_SIGNATURE_DETECTION}，跳过签名检测")
            return markdown_content

        page_texts = self._extract_page_texts(file_path)
        signature_lines = self._find_signature_lines(page_texts)

        if not signature_lines:
            return markdown_content

        lines = markdown_content.split('\n')
        filtered_lines = []
        skip_count = 0

        for line in lines:
            stripped = line.strip()
            if stripped in signature_lines:
                skip_count += 1
                continue
            filtered_lines.append(line)

        if skip_count > 0:
            logger.info(f"已移除 {skip_count} 行签名/页眉/页脚内容")

        return '\n'.join(filtered_lines)


class TXTConverter(BaseConverter):

    def to_markdown(self, file_path: str, ai_assist: bool = False) -> str:
        """TXT转Markdown"""
        logger.info(f"开始转换TXT: {file_path} (Python优化: {ai_assist})")

        try:
            raw_content = read_file_with_encoding(file_path)

            markdown_content = clean_text(raw_content)

            if ai_assist:
                logger.info("使用Python进行额外优化...")
                markdown_content = clean_markdown_content(markdown_content)
                markdown_content = optimize_markdown_format(markdown_content)

            markdown_content = remove_images_from_markdown(markdown_content)

            logger.info(f"TXT转换完成: {file_path}")
            return markdown_content
            
        except Exception as e:
            logger.error(f"TXT转换失败: {e}")
            raise


class DOCXConverter(BaseConverter):
    """Word文档转Markdown转换器（使用mammoth）"""

    SUPPORTED_FORMATS = ['.docx']

    def to_markdown(self, file_path: str, ai_assist: bool = False) -> str:
        """将Word文档转换为Markdown（默认启用Python优化）"""
        logger.info(f"开始转换Word文档: {file_path} (Python优化: {ai_assist})")

        try:
            markdown_content = self._extract_docx_text(file_path)
            markdown_content = clean_text(markdown_content)

            if ai_assist:
                logger.info("使用Python进行Word文档内容优化...")
                markdown_content = clean_markdown_content(markdown_content)
                markdown_content = optimize_markdown_format(markdown_content)

            markdown_content = remove_images_from_markdown(markdown_content)

            logger.info(f"Word文档转换完成: {file_path}")
            return markdown_content

        except Exception as e:
            logger.error(f"Word文档转换失败 {file_path}: {e}")
            raise

    def _extract_docx_text(self, file_path: str) -> str:
        """使用mammoth将DOCX转换为Markdown"""
        import mammoth
        with open(file_path, 'rb') as docx_file:
            result = mammoth.convert_to_markdown(docx_file)
            return result.value


class FileConverterManager:
    """文件转换管理器"""

    PDF_FORMATS = ['.pdf']
    DOCX_FORMATS = ['.docx']
    TXT_FORMATS = ['.txt']

    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback
        self._pdf_converter = None
        self._docx_converter = None
        self._txt_converter = None

    @property
    def pdf_converter(self):
        """懒加载PDF转换器"""
        if self._pdf_converter is None:
            self._pdf_converter = PDFConverter(self.progress_callback)
        return self._pdf_converter

    @property
    def docx_converter(self):
        """懒加载Word文档转换器"""
        if self._docx_converter is None:
            self._docx_converter = DOCXConverter(self.progress_callback)
        return self._docx_converter

    @property
    def txt_converter(self):
        """懒加载TXT转换器"""
        if self._txt_converter is None:
            self._txt_converter = TXTConverter(self.progress_callback)
        return self._txt_converter

    def _get_converter(self, ext: str):
        """根据扩展名获取合适的转换器"""
        ext = ext.lower()
        if ext in self.PDF_FORMATS:
            return self.pdf_converter
        elif ext in self.DOCX_FORMATS:
            return self.docx_converter
        elif ext in self.TXT_FORMATS:
            return self.txt_converter
        else:
            return None
    
    def convert_file(
        self, 
        file_path: str, 
        output_path: str,
        output_format: str = 'markdown',
        ai_assist: bool = False
    ) -> Dict:
        """
        转换单个文件
        
        Args:
            file_path: 输入文件路径
            output_path: 输出目录路径
            output_format: 输出格式（目前仅支持 markdown）
            ai_assist: 是否使用AI进行额外优化（默认False）
        """
        result = {
            'file_path': file_path,
            'success': False,
            'output_path': None,
            'error': None
        }
        
        try:
            file_path_obj = Path(file_path)
            
            if not file_path_obj.exists():
                result['error'] = "文件不存在"
                return result
            
            ext = get_file_extension(file_path_obj.name)
            converter = self._get_converter(ext)
            
            if converter is None:
                result['error'] = f"不支持的文件格式: {ext}"
                return result
            
            # 转换为Markdown
            markdown_content = converter.to_markdown(str(file_path), ai_assist=ai_assist)
            
            # 保存文件
            output_dir = ensure_dir(output_path)
            output_filename = sanitize_filename(file_path_obj.stem) + '.md'
            output_file = output_dir / output_filename

            counter = 1
            original_output_file = output_file
            while output_file.exists():
                stem = original_output_file.stem
                output_file = original_output_file.parent / f"{stem}_{counter}.md"
                counter += 1

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)

            result['success'] = True
            result['output_path'] = str(output_file)

            logger.info(f"文件转换成功: {output_file}")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"文件转换失败: {e}")
        
        return result
    
    def convert_batch(
        self,
        file_paths: List[str],
        output_path: str,
        raw_path: str = None,
        output_format: str = 'markdown',
        ai_assist: bool = False
    ) -> List[Dict]:
        """批量转换文件"""
        results = []
        total = len(file_paths)

        for i, file_path in enumerate(file_paths):
            if self.progress_callback:
                self.progress_callback(i + 1, total, f"正在转换: {Path(file_path).name}")

            result = self.convert_file(file_path, output_path, output_format, ai_assist=ai_assist)

            if result['success'] and raw_path:
                self._move_to_raw(file_path, raw_path)

            results.append(result)

        if self.progress_callback:
            success_count = sum(1 for r in results if r['success'])
            self.progress_callback(total, total, f"转换完成: {success_count}/{total} 成功")

        return results

    def _move_to_raw(self, file_path: str, raw_path: str) -> bool:
        """移动文件到Raw文件夹进行归档"""
        try:
            source = Path(file_path)
            if not source.exists():
                logger.warning(f"源文件不存在，跳过移动: {file_path}")
                return False

            raw_dir = Path(raw_path)
            raw_dir.mkdir(parents=True, exist_ok=True)

            dest = raw_dir / source.name
            if dest.exists():
                base_name = source.stem
                extension = source.suffix
                counter = 1
                while dest.exists():
                    dest = raw_dir / f"{base_name}_{counter}{extension}"
                    counter += 1

            import shutil
            shutil.move(str(source), str(dest))
            logger.info(f"已移动文件到Raw: {source} -> {dest}")
            return True
        except Exception as e:
            logger.error(f"移动文件到Raw失败: {file_path}, 错误: {e}")
            return False
    
    def convert_folder(
        self,
        folder_path: str,
        output_path: str,
        raw_path: str = None,
        output_format: str = 'markdown',
        recursive: bool = True,
        ai_assist: bool = False
    ) -> List[Dict]:
        """转换整个文件夹"""
        folder = Path(folder_path)

        if not folder.exists():
            logger.error(f"文件夹不存在: {folder_path}")
            return [{
                'file_path': folder_path,
                'success': False,
                'output_path': None,
                'error': f"文件夹不存在: {folder_path}"
            }]

        file_paths = []
        all_files = list(folder.rglob('*') if recursive else folder.glob('*'))

        for file_path in all_files:
            if file_path.is_file() and not file_path.name.startswith('.'):
                relative_path = file_path.relative_to(folder)
                if RAW_FOLDER in relative_path.parts:
                    continue
                ext = file_path.suffix.lower()
                if ext != '.md' and ext in self.get_supported_formats():
                    file_paths.append(str(file_path))

        file_paths = [str(p) for p in file_paths]

        logger.info(f"找到 {len(file_paths)} 个可转换文件")

        return self.convert_batch(file_paths, output_path, raw_path, output_format, ai_assist=ai_assist)
    
    @classmethod
    def get_supported_formats(cls) -> List[str]:
        """获取支持的格式列表"""
        return cls.PDF_FORMATS + cls.DOCX_FORMATS + cls.TXT_FORMATS
