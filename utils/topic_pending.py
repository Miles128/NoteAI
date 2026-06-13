import json
import threading
from pathlib import Path

from config import config
from utils.logger import logger
from utils.text_utils import parse_frontmatter
from utils.topic_file_ops import _check_topic_needs_processing

_pending_lock = threading.Lock()


def _get_pending_path():
    workspace = config.workspace_path
    if not workspace:
        return None
    return Path(workspace) / ".pending_topics.json"


def get_pending_path():
    return _get_pending_path()


def load_pending():
    with _pending_lock:
        path = _get_pending_path()
        if not path or not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"[topic_assigner] load_pending failed: {e}")
            return []


def save_pending(pending):
    with _pending_lock:
        path = _get_pending_path()
        if not path:
            return
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)


def _drop_pending_for_rel(rel_path: str) -> None:
    pending = load_pending()
    filtered = [p for p in pending if p.get("file") != rel_path]
    if len(filtered) != len(pending):
        save_pending(filtered)


def cleanup_stale_pending():
    workspace = config.workspace_path
    if not workspace:
        return 0
    pending = load_pending()
    if not pending:
        return 0
    ws = Path(workspace)
    original_count = len(pending)
    valid = []
    seen = set()
    for p in pending:
        file_path = p.get("file", "")
        if not file_path:
            continue
        if file_path in seen:
            continue
        seen.add(file_path)
        full = ws / file_path if not Path(file_path).is_absolute() else Path(file_path)
        if not full.exists():
            logger.info(f"[topic_assigner] 清理无效待办: {file_path} 文件已不存在")
            continue
        try:
            text = full.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            if meta is not None and not _check_topic_needs_processing(meta):
                logger.info(f"[topic_assigner] 清理已处理待办: {file_path} 已有主题")
                continue
        except Exception as e:
            logger.error(f"[cleanup_stale] read failed: {e}")
        valid.append(p)
    removed = original_count - len(valid)
    if removed > 0:
        save_pending(valid)
    return removed
