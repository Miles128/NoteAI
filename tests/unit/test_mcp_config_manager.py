import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sidecar.mcp_config_manager import (
    MCP_SERVER_NAME,
    build_mcp_server_config,
    get_mcp_status,
    register_mcp_server,
    unregister_mcp_server,
)


class TestMcpConfigManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "vault"
        self.workspace.mkdir()
        self.script = self.root / "mcp-server" / "src" / "index.js"
        self.script.parent.mkdir(parents=True)
        self.script.write_text("// stub\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _patch_script(self):
        return patch(
            "sidecar.mcp_config_manager._mcp_server_script",
            return_value=self.script,
        )

    def _patch_home(self, home: Path):
        return patch("sidecar.mcp_config_manager._user_home", return_value=home)

    def test_register_standard_json_targets(self):
        home = self.root / "home"
        with self._patch_script(), self._patch_home(home):
            result = register_mcp_server(
                targets=["claude", "kimi"],
                workspace_path=str(self.workspace),
            )
        self.assertTrue(result["success"])
        self.assertEqual(sorted(result["registered"]), ["claude", "kimi"])

        claude_cfg = (home / ".claude" / "mcp.json").read_text(encoding="utf-8")
        self.assertIn(MCP_SERVER_NAME, claude_cfg)
        self.assertIn(str(self.workspace.resolve()), claude_cfg)

    def test_register_opencode_format(self):
        home = self.root / "home"
        config_dir = home / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        (config_dir / "opencode.json").write_text('{"mcp": {}}', encoding="utf-8")

        with self._patch_script(), self._patch_home(home):
            result = register_mcp_server(
                targets=["opencode"],
                workspace_path=str(self.workspace),
            )
        self.assertTrue(result["success"])

        import json

        data = json.loads((config_dir / "opencode.json").read_text(encoding="utf-8"))
        entry = data["mcp"][MCP_SERVER_NAME]
        self.assertEqual(entry["type"], "local")
        self.assertEqual(entry["command"][0], "node")
        self.assertTrue(entry["enabled"])

    def test_register_codex_toml(self):
        home = self.root / "home"
        codex_dir = home / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "config.toml").write_text('model = "gpt-5"\n', encoding="utf-8")

        with self._patch_script(), self._patch_home(home):
            result = register_mcp_server(
                targets=["codex"],
                workspace_path=str(self.workspace),
            )
        self.assertTrue(result["success"])

        content = (codex_dir / "config.toml").read_text(encoding="utf-8")
        self.assertIn(f"[mcp_servers.{MCP_SERVER_NAME}]", content)
        self.assertIn('command = "node"', content)

    def test_unregister_and_status(self):
        home = self.root / "home"
        with self._patch_script(), self._patch_home(home):
            register_mcp_server(
                targets=["gemini"],
                workspace_path=str(self.workspace),
            )
            status = get_mcp_status()
            self.assertTrue(status["gemini"]["registered"])

            removed = unregister_mcp_server(targets=["gemini"])
            self.assertIn("gemini", removed["removed"])
            status = get_mcp_status()
            self.assertFalse(status["gemini"]["registered"])

    def test_build_mcp_server_config_requires_workspace(self):
        with self._patch_script(), patch("sidecar.mcp_config_manager.config") as mock_config:
            mock_config.workspace_path = ""
            with self.assertRaises(ValueError):
                build_mcp_server_config()


if __name__ == "__main__":
    unittest.main()
