import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PROJECT_CONFIG_PATH = str(Path(__file__).parent / "config.json")


def get_system_app_data_dir() -> Path:
    app_name = "NoteAI"

    if sys.platform == "darwin":
        base_dir = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base_dir = Path.home() / ".config"

    return base_dir / app_name


SYSTEM_APP_DATA_DIR = get_system_app_data_dir()
WORKSPACE_STATE_FILE = SYSTEM_APP_DATA_DIR / "workspace_state.json"
API_CONFIG_FILE = SYSTEM_APP_DATA_DIR / "api_config.json"

NOTES_FOLDER = "Notes"
ABSTRACT_FOLDER = "wiki"
RAW_FOLDER = "Raw"
USED_FOLDER = "Used"
WORKSPACE_APP_FOLDER = ".noteai"
RAG_INDEX_FOLDER = "rag_index"

TOPIC_SEP = " > "

IGNORED_DIRS = {
    "ai",
    "noteai",
    ".noteai",
    ".NoteAI",
    "wiki",
    "ai wiki",
    "ai-wiki",
    "ai_wiki",
    "aiwiki",
}


def is_ignored_dir(dir_name: str) -> bool:
    if not dir_name:
        return False
    return dir_name.lower() in IGNORED_DIRS
