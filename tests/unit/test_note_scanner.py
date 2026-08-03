import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.note_scanner import iter_note_files


class IterNoteFilesTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        self.notes = self.ws / "Notes"
        self.notes.mkdir()
        (self.notes / "普通笔记.md").write_text("a", encoding="utf-8")
        (self.notes / "sub").mkdir()
        (self.notes / "sub" / "嵌套笔记.md").write_text("b", encoding="utf-8")
        (self.notes / "主题_综述.md").write_text("survey", encoding="utf-8")
        (self.notes / ".隐藏.md").write_text("hidden", encoding="utf-8")
        (self.notes / "not-markdown.txt").write_text("txt", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def names(self, **kwargs):
        return sorted(p.name for p in iter_note_files(self.ws, **kwargs))


class TestIterNoteFilesDefaults(IterNoteFilesTestBase):
    def test_default_excludes_surveys_hidden_and_non_md(self):
        self.assertEqual(self.names(), sorted(["普通笔记.md", "嵌套笔记.md"]))

    def test_default_recursive(self):
        names = self.names()
        self.assertIn("嵌套笔记.md", names)
        self.assertNotIn("not-markdown.txt", names)


class TestIterNoteFilesFlags(IterNoteFilesTestBase):
    def test_include_surveys(self):
        names = self.names(include_surveys=True)
        self.assertIn("主题_综述.md", names)

    def test_include_hidden(self):
        names = self.names(include_hidden=True)
        self.assertIn(".隐藏.md", names)

    def test_missing_folder_returns_empty(self):
        result = iter_note_files(self.ws, folders=["NotExist"])
        self.assertEqual(result, [])

    def test_custom_folders(self):
        other = self.ws / "Inbox"
        other.mkdir()
        (other / "收件.md").write_text("c", encoding="utf-8")
        result = iter_note_files(self.ws, folders=["Inbox"])
        self.assertEqual([p.name for p in result], ["收件.md"])

    def test_nonexistent_workspace(self):
        result = iter_note_files(self.ws / "missing-ws")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
