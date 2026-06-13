from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEBUI = ROOT / "webui"


def test_index_referenced_local_assets_exist() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r"""(?:src|href)=["']([^"']+)["']""", html)

    missing = []
    for ref in refs:
        if ref.startswith(("http://", "https://", "data:", "#")):
            continue
        asset = WEBUI / ref.split("?", 1)[0]
        if not asset.exists():
            missing.append(ref)

    assert missing == []


def test_required_generated_assets_are_not_gitignored() -> None:
    required = ["webui/lib/tiptap-bundle.js"]
    result = subprocess.run(
        ["git", "check-ignore", *required],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.stdout.strip() == ""


def test_node_modules_is_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "node_modules"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == ""
