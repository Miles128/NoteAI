import json
import time
from pathlib import Path

import pytest

from config import config
from config.settings import WORKSPACE_APP_FOLDER
from utils.activity_log import add_entry, get_entries
from utils.workspace_log import append_log, migrate_legacy_logs, parse_log_entries


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "wiki").mkdir(parents=True)
    config.workspace_path = str(d)
    return d


def test_append_and_parse_log(workspace: Path) -> None:
    append_log("ingest", "测试入库", "Notes/foo.md")
    log_path = workspace / "wiki" / "log.md"
    assert log_path.exists()
    text = log_path.read_text(encoding="utf-8")
    assert "**INGEST**" in text
    assert "测试入库" in text

    entries = parse_log_entries(10)
    assert entries[-1]["msg"] == "测试入库"
    assert entries[-1]["type"] == "ingest"


def test_activity_log_compat(workspace: Path) -> None:
    add_entry("convert", "转换完成", "a.pdf")
    rows = get_entries(5)
    assert rows[-1]["msg"] == "转换完成"


def test_migrate_legacy_activity_json(workspace: Path) -> None:
    legacy = workspace / WORKSPACE_APP_FOLDER / "activity_log.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps(
            [
                {
                    "ts": time.time(),
                    "type": "move",
                    "msg": "旧日志条目",
                    "detail": "Notes/x.md",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = migrate_legacy_logs(str(workspace))
    assert result["success"] is True
    assert result["migrated"] == 1
    assert not legacy.exists()
    assert (workspace / "wiki" / "log.md").exists()
    assert "旧日志条目" in (workspace / "wiki" / "log.md").read_text(encoding="utf-8")
