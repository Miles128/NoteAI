import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.helpers import (
    sanitize_filename, clean_text, remove_images_from_markdown,
    extract_title_from_markdown, split_text_into_chunks, truncate_text,
    get_file_extension, validate_api_key, detect_language,
    recursive_markdown_chunk, smart_truncate_text, _truncate_at_sentence_boundary
)


class TestSanitizeFilename(unittest.TestCase):
    def test_remove_invalid_chars(self):
        self.assertEqual(sanitize_filename('file<>name.txt'), 'file__name.txt')
    
    def test_max_length(self):
        long_name = 'a' * 200 + '.txt'
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 100)
    
    def test_empty_name(self):
        self.assertEqual(sanitize_filename('   '), 'unnamed')


class TestCleanText(unittest.TestCase):
    def test_remove_control_chars(self):
        text = 'hello\x00world'
        self.assertEqual(clean_text(text), 'helloworld')
    
    def test_normalize_whitespace(self):
        text = 'hello   world\n\nnew line'
        self.assertEqual(clean_text(text), 'hello world new line')


class TestRemoveImages(unittest.TestCase):
    def test_remove_markdown_images(self):
        md = '![alt](http://example.com/img.png)'
        self.assertEqual(remove_images_from_markdown(md), '')
    
    def test_remove_html_images(self):
        md = '<img src="http://example.com/img.png" />'
        self.assertEqual(remove_images_from_markdown(md), '')


class TestExtractTitle(unittest.TestCase):
    def test_h1_title(self):
        md = '# My Title\n\nContent'
        self.assertEqual(extract_title_from_markdown(md), 'My Title')
    
    def test_h2_title(self):
        md = '## My Title\n\nContent'
        self.assertEqual(extract_title_from_markdown(md), 'My Title')
    
    def test_no_title(self):
        md = 'Just content'
        self.assertIsNone(extract_title_from_markdown(md))


class TestSplitText(unittest.TestCase):
    def test_basic_split(self):
        text = 'A' * 2000
        chunks = split_text_into_chunks(text, chunk_size=1000, overlap=200)
        self.assertGreater(len(chunks), 1)
    
    def test_small_text(self):
        text = 'Small text'
        chunks = split_text_into_chunks(text, chunk_size=1000)
        self.assertEqual(len(chunks), 1)


class TestTruncateText(unittest.TestCase):
    def test_truncate(self):
        text = 'A' * 200
        result = truncate_text(text, max_length=50)
        self.assertEqual(len(result), 50)
        self.assertTrue(result.endswith('...'))
    
    def test_no_truncate(self):
        text = 'Short'
        result = truncate_text(text, max_length=100)
        self.assertEqual(result, 'Short')


class TestGetFileExtension(unittest.TestCase):
    def test_pdf(self):
        self.assertEqual(get_file_extension('file.pdf'), '.pdf')
    
    def test_uppercase(self):
        self.assertEqual(get_file_extension('file.PDF'), '.pdf')


class TestValidateApiKey(unittest.TestCase):
    def test_valid_key(self):
        self.assertTrue(validate_api_key('sk-1234567890abcdef'))
    
    def test_empty_key(self):
        self.assertFalse(validate_api_key(''))
    
    def test_short_key(self):
        self.assertFalse(validate_api_key('short'))
    
    def test_whitespace_key(self):
        self.assertFalse(validate_api_key('   '))


class TestDetectLanguage(unittest.TestCase):
    def test_chinese(self):
        text = '这是一个中文测试'
        self.assertEqual(detect_language(text), 'chinese')
    
    def test_english(self):
        text = 'This is an English test'
        self.assertEqual(detect_language(text), 'english')
    
    def test_empty(self):
        self.assertEqual(detect_language(''), 'unknown')


class TestMaxContextTokens(unittest.TestCase):
    def test_default_max_context_tokens(self):
        from config.settings import AppConfig
        config = AppConfig()
        self.assertEqual(config.max_context_tokens, 128000)
    
    def test_validate_context_config_valid(self):
        from config.settings import AppConfig
        config = AppConfig(max_context_tokens=131072)
        self.assertTrue(config.validate_context_config())
    
    def test_validate_context_config_too_small(self):
        from config.settings import AppConfig
        config = AppConfig(max_context_tokens=500)
        self.assertFalse(config.validate_context_config())
    
    def test_validate_context_config_too_large(self):
        from config.settings import AppConfig
        config = AppConfig(max_context_tokens=2000000)
        self.assertFalse(config.validate_context_config())
    
    def test_check_content_within_limit_small(self):
        from config.settings import AppConfig
        config = AppConfig(max_context_tokens=131072)
        content = 'This is a short test content'
        is_within, tokens, result = config.check_content_within_context(content)
        self.assertTrue(is_within)
        self.assertEqual(result, content)
    
    def test_check_content_truncation(self):
        from config.settings import AppConfig
        config = AppConfig(max_context_tokens=1000, model_name='gpt-4')
        content = 'A' * 10000
        is_within, tokens, result = config.check_content_within_context(content)
        self.assertFalse(is_within)
        self.assertGreater(tokens, 1000)
        self.assertIn('内容已截断', result)


class TestRecursiveMarkdownChunk(unittest.TestCase):
    def test_small_text_no_split(self):
        text = "# Title\n\nSmall content here."
        chunks = recursive_markdown_chunk(text, chunk_size=1000, overlap=200)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)
    
    def test_split_by_headings(self):
        text = """# Heading 1

Content for heading 1. This is a long paragraph that should be part of the first section. It contains multiple sentences to make it longer.

## Heading 2

Content for heading 2. Another long paragraph for the second section. This also has multiple sentences.

## Heading 3

Content for heading 3. Final section content."""
        
        chunks = recursive_markdown_chunk(text, chunk_size=100, overlap=20)
        self.assertGreater(len(chunks), 1)
        
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 150)
    
    def test_split_by_punctuation(self):
        text = "This is sentence one. This is sentence two. This is sentence three. This is sentence four. This is sentence five. This is sentence six. This is sentence seven. This is sentence eight. This is sentence nine. This is sentence ten."
        
        chunks = recursive_markdown_chunk(text, chunk_size=50, overlap=10)
        self.assertGreater(len(chunks), 1)
        
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 75)
    
    def test_preserves_heading_context(self):
        text = """# Main Topic

This is a very long paragraph under the main topic that exceeds the chunk size limit. It should be split while preserving the heading context in each chunk. More content here to make it longer. Additional sentences to increase the length. Even more content to ensure it exceeds the limit."""
        
        chunks = recursive_markdown_chunk(text, chunk_size=100, overlap=20)
        
        for chunk in chunks:
            self.assertIn('# Main Topic', chunk)
    
    def test_nested_headings(self):
        text = """# Level 1

Some content at level 1.

## Level 2

Very long content at level 2 that needs to be split into multiple chunks. This paragraph is quite long and should trigger the recursive splitting mechanism. More text here. Even more text. And some more.

### Level 3

Content at level 3. Also very long and needs splitting. More sentences. More content. Additional text."""
        
        chunks = recursive_markdown_chunk(text, chunk_size=80, overlap=15)
        self.assertGreater(len(chunks), 1)
    
    def test_chinese_text(self):
        text = """# 中文标题

这是第一段内容。内容很长，需要被分割。这是第二个句子。这是第三个句子。这是第四个句子。这是第五个句子。这是第六个句子。这是第七个句子。这是第八个句子。

## 第二个标题

第二段内容。同样需要被分割。继续添加内容。更多内容。更多句子。"""
        
        chunks = recursive_markdown_chunk(text, chunk_size=50, overlap=10)
        self.assertGreater(len(chunks), 1)
    
    def test_overlap_between_chunks(self):
        text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
        
        chunks = recursive_markdown_chunk(text, chunk_size=30, overlap=10)
        
        if len(chunks) > 1:
            for i in range(1, len(chunks)):
                prev_chunk = chunks[i-1]
                curr_chunk = chunks[i]
                has_overlap = any(
                    prev_chunk.endswith(text[j:j+10]) and curr_chunk.startswith(text[j:j+10])
                    for j in range(len(text) - 10)
                )
                self.assertTrue(has_overlap or len(chunks) == 1)


class TestSmartTruncateText(unittest.TestCase):
    def test_no_truncation_needed(self):
        text = "Short text"
        result = smart_truncate_text(text, max_length=100)
        self.assertEqual(result, text)
    
    def test_truncation_with_headings(self):
        text = """# Main Title

Important content here. This should be preserved.

## Secondary Title

More important details.

### Tertiary Title

Less important details that might be truncated."""
        
        result = smart_truncate_text(text, max_length=100)
        self.assertIn('# Main Title', result)
        self.assertLessEqual(len(result), 100)
    
    def test_truncation_at_sentence_boundary(self):
        text = "This is the first sentence. This is the second sentence. This is the third sentence. This is the fourth sentence."
        
        result = smart_truncate_text(text, max_length=50)
        self.assertLessEqual(len(result), 50)
        self.assertTrue(result.endswith('...'))
    
    def test_preserves_markdown_structure(self):
        text = """# Title

Paragraph one with important info.

Paragraph two with more details.

Paragraph three with additional context."""
        
        result = smart_truncate_text(text, max_length=80)
        self.assertIn('# Title', result)
        self.assertLessEqual(len(result), 80)
    
    def test_chinese_text_truncation(self):
        text = "这是第一段内容，包含重要信息。这是第二段内容。这是第三段内容。这是第四段内容。"
        
        result = smart_truncate_text(text, max_length=30)
        self.assertLessEqual(len(result), 30)


class TestTruncateAtSentenceBoundary(unittest.TestCase):
    def test_no_truncation(self):
        text = "Short sentence."
        result = _truncate_at_sentence_boundary(text, 100)
        self.assertEqual(result, text)
    
    def test_truncate_at_period(self):
        text = "First sentence. Second sentence. Third sentence."
        result = _truncate_at_sentence_boundary(text, 20)
        self.assertIn('.', result)
        self.assertLessEqual(len(result), 20)
    
    def test_truncate_at_chinese_period(self):
        text = "第一句。第二句。第三句。"
        result = _truncate_at_sentence_boundary(text, 10)
        self.assertIn('。', result)
        self.assertLessEqual(len(result), 10)
    
    def test_forced_truncation(self):
        text = "This is a very long sentence without any punctuation"
        result = _truncate_at_sentence_boundary(text, 20)
        self.assertLessEqual(len(result), 20)


if __name__ == '__main__':
    unittest.main()
