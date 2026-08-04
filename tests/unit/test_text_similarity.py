import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sidecar.text_similarity import (
    SHINGLE_SIZE,
    bounded,
    jaccard,
    normalize_body,
    shingles,
    simhash,
)


class TestBounded(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(bounded("hello", 10), "hello")

    def test_exact_limit_unchanged(self):
        text = "a" * 10
        self.assertEqual(bounded(text, 10), text)

    def test_long_text_keeps_head_and_tail(self):
        text = "".join(str(i % 10) for i in range(100))
        result = bounded(text, 20)
        self.assertEqual(len(result), 20)
        self.assertEqual(result[:10], text[:10])
        self.assertEqual(result[-10:], text[-10:])


class TestNormalizeBody(unittest.TestCase):
    def test_lowercases_and_strips_punctuation(self):
        self.assertEqual(normalize_body("Hello, World! 你好。"), "helloworld你好")

    def test_strips_whitespace_and_underscores(self):
        self.assertEqual(normalize_body("a_b c\nd"), "abcd")

    def test_truncates_to_max_chars_before_stripping(self):
        text = "x" * 100 + "y" * 100
        result = normalize_body(text, max_chars=50)
        self.assertEqual(result, "x" * 25 + "y" * 25)

    def test_empty_input(self):
        self.assertEqual(normalize_body(""), "")


class TestShingles(unittest.TestCase):
    def test_short_text_returns_empty(self):
        self.assertEqual(shingles("abc", size=SHINGLE_SIZE), set())

    def test_exact_size_text_single_shingle(self):
        text = "abcde"
        self.assertEqual(shingles(text, size=SHINGLE_SIZE), {"abcde"})

    def test_full_coverage_small_text(self):
        text = "abcdefg"  # len 7, size 5 -> 3 shingles
        self.assertEqual(shingles(text, size=SHINGLE_SIZE), {"abcde", "bcdef", "cdefg"})

    def test_max_count_bounds_sampling(self):
        text = "".join(chr(ord("a") + i % 26) for i in range(2000))
        result = shingles(text, size=SHINGLE_SIZE, max_count=100)
        self.assertLessEqual(len(result), 100)
        self.assertGreater(len(result), 0)
        for shingle in result:
            self.assertEqual(len(shingle), SHINGLE_SIZE)


class TestSimhash(unittest.TestCase):
    def test_empty_set_is_zero(self):
        self.assertEqual(simhash(set()), 0)

    def test_deterministic(self):
        s = shingles(normalize_body("重复内容检测的最小示例文本" * 5))
        self.assertEqual(simhash(s), simhash(s))

    def test_within_64_bits(self):
        s = shingles(normalize_body("another sample text for fingerprint bounds"))
        value = simhash(s)
        self.assertGreaterEqual(value, 0)
        self.assertLess(value, 1 << 64)

    def test_identical_sets_identical_hash(self):
        a = shingles(normalize_body("shared body content one two three"))
        b = shingles(normalize_body("SHARED body content, one two three!"))
        self.assertEqual(simhash(a), simhash(b))


class TestJaccard(unittest.TestCase):
    def test_empty_sets_return_zero(self):
        self.assertEqual(jaccard(set(), set()), 0.0)
        self.assertEqual(jaccard({"a"}, set()), 0.0)
        self.assertEqual(jaccard(set(), {"a"}), 0.0)

    def test_identical_sets_return_one(self):
        self.assertEqual(jaccard({"a", "b"}, {"a", "b"}), 1.0)

    def test_known_value(self):
        # {a,b} vs {b,c} -> 1 / 3
        self.assertAlmostEqual(jaccard({"a", "b"}, {"b", "c"}), 1 / 3)

    def test_disjoint_sets_return_zero(self):
        self.assertEqual(jaccard({"a"}, {"b"}), 0.0)


if __name__ == "__main__":
    unittest.main()
