import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.helpers import (
    _truncate_at_sentence_boundary,
    clean_text,
    extract_title_from_markdown,
    get_file_extension,
    remove_images_from_markdown,
    sanitize_filename,
    smart_truncate_text,
)


class TestSanitizeFilename(unittest.TestCase):
    def test_remove_invalid_chars(self):
        self.assertEqual(sanitize_filename("file<>name.txt"), "file__name.txt")

    def test_max_length(self):
        long_name = "a" * 200 + ".txt"
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 100)

    def test_empty_name(self):
        self.assertEqual(sanitize_filename("   "), "unnamed")


class TestCleanText(unittest.TestCase):
    def test_remove_control_chars(self):
        text = "hello\x00world"
        self.assertEqual(clean_text(text), "helloworld")

    def test_normalize_whitespace(self):
        text = "hello   world\n\nnew line"
        self.assertEqual(clean_text(text), "hello world new line")


class TestRemoveImages(unittest.TestCase):
    def test_remove_markdown_images(self):
        md = "![alt](http://example.com/img.png)"
        self.assertEqual(remove_images_from_markdown(md), "")

    def test_remove_html_images(self):
        md = '<img src="http://example.com/img.png" />'
        self.assertEqual(remove_images_from_markdown(md), "")


class TestExtractTitle(unittest.TestCase):
    def test_h1_title(self):
        md = "# My Title\n\nContent"
        self.assertEqual(extract_title_from_markdown(md), "My Title")

    def test_h2_title(self):
        md = "## My Title\n\nContent"
        self.assertEqual(extract_title_from_markdown(md), "My Title")

    def test_no_title(self):
        md = "Just content"
        self.assertIsNone(extract_title_from_markdown(md))


class TestGetFileExtension(unittest.TestCase):
    def test_pdf(self):
        self.assertEqual(get_file_extension("file.pdf"), ".pdf")

    def test_uppercase(self):
        self.assertEqual(get_file_extension("file.PDF"), ".pdf")


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
        from utils.llm_utils import check_content_within_context

        content = "This is a short test content"
        is_within, tokens, result = check_content_within_context(content, max_context_tokens=131072)
        self.assertTrue(is_within)
        self.assertEqual(result, content)

    def test_check_content_truncation(self):
        from unittest.mock import patch

        from utils.llm_utils import check_content_within_context

        content = "A" * 10000
        with patch(
            "utils.llm_utils.process_content_with_llm",
            return_value=("truncated summary", True, True, 400),
        ):
            is_within, tokens, result = check_content_within_context(
                content, max_context_tokens=1000, model_name="gpt-4"
            )
        self.assertFalse(is_within)
        self.assertLess(tokens, 1000)
        self.assertNotEqual(result, content)


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
        self.assertIn("# Main Title", result)
        self.assertLessEqual(len(result), 100)

    def test_truncation_at_sentence_boundary(self):
        text = "This is the first sentence. This is the second sentence. This is the third sentence. This is the fourth sentence."

        result = smart_truncate_text(text, max_length=50)
        self.assertLessEqual(len(result), 50)
        self.assertTrue(result.endswith("..."))

    def test_preserves_markdown_structure(self):
        text = """# Title

Paragraph one with important info.

Paragraph two with more details.

Paragraph three with additional context."""

        result = smart_truncate_text(text, max_length=80)
        self.assertIn("# Title", result)
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
        self.assertIn(".", result)
        self.assertLessEqual(len(result), 20)

    def test_truncate_at_chinese_period(self):
        text = "第一句。第二句。第三句。"
        result = _truncate_at_sentence_boundary(text, 10)
        self.assertIn("。", result)
        self.assertLessEqual(len(result), 10)

    def test_forced_truncation(self):
        text = "This is a very long sentence without any punctuation"
        result = _truncate_at_sentence_boundary(text, 20)
        self.assertLessEqual(len(result), 20)


if __name__ == "__main__":
    unittest.main()
