import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils import component_state, deps_sync


class TestComponentState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp.name) / "components.json"
        self._patch = patch.object(component_state, "_COMPONENTS_FILE", self.state_file)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.tmp.cleanup()

    def test_rag_not_removed_by_default(self):
        self.assertFalse(component_state.is_component_removed("rag"))

    def test_set_removed_persists(self):
        component_state.set_component_removed("rag", True)
        self.assertTrue(component_state.is_component_removed("rag"))
        component_state.set_component_removed("rag", False)
        self.assertFalse(component_state.is_component_removed("rag"))

    def test_default_sync_includes_rag(self):
        extras = deps_sync.default_sync_extras()
        self.assertIn("dev", extras)
        self.assertIn("rag", extras)

    def test_sync_excludes_rag_when_user_removed(self):
        component_state.set_component_removed("rag", True)
        extras = deps_sync.default_sync_extras()
        self.assertIn("dev", extras)
        self.assertNotIn("rag", extras)

    def test_recommended_sync_command(self):
        cmd = deps_sync.recommended_sync_command()
        self.assertIn("uv sync", cmd)
        self.assertIn("--extra rag", cmd)


if __name__ == "__main__":
    unittest.main()
