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


def test_job_and_status_api_methods_are_allowed_by_tauri_rpc() -> None:
    api_js = (WEBUI / "js" / "api.js").read_text(encoding="utf-8")
    rpc_rs = (ROOT / "src-tauri" / "src" / "rpc.rs").read_text(encoding="utf-8")
    allowed_block = rpc_rs.split("static ALLOWED_PYTHON_METHODS", 1)[1].split("];", 1)[0]
    allowed = set(re.findall(r'"([a-zA-Z0-9_]+)"', allowed_block))

    required = {"get_jobs", "get_job", "get_link_stats", "run_kb_lint"}
    declared = set(re.findall(r"""method:\s*['"]([^'"]+)['"]""", api_js))

    assert required <= declared
    assert required <= allowed
