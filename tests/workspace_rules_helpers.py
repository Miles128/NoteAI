"""Shared helpers for workspace rules in tests."""

from __future__ import annotations

import json
from pathlib import Path

from config.settings import WORKSPACE_APP_FOLDER
from sidecar.workspace_rules import RULES_FILENAME


def write_workspace_rules(workspace: Path, **overrides) -> Path:
    data = {
        "max_topic_depth": 3,
        "auto_update_survey": True,
        "survey_at_level": 2,
        "ai_may_edit_wiki": True,
        "ai_may_edit_notes": False,
        "configured": True,
    }
    data.update(overrides)
    path = workspace / WORKSPACE_APP_FOLDER / RULES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
