import json
import threading
from pathlib import Path

from config import config
from utils.logger import logger

_LOCK = threading.Lock()
_MAX_LONG_MEMORY_CHARS = 1500


def _memory_dir():
    ws = config.workspace_path
    if not ws:
        return None
    d = Path(ws) / ".ai_memory"
    d.mkdir(exist_ok=True)
    return d


def _long_memory_path():
    d = _memory_dir()
    return d / "long_memory.json" if d else None


def _short_memory_path():
    d = _memory_dir()
    return d / "short_memory.json" if d else None


def load_long_memory():
    p = _long_memory_path()
    if not p or not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("content", "")
    except Exception:
        return ""


def save_long_memory(content):
    p = _long_memory_path()
    if not p:
        return
    p.write_text(json.dumps({"content": content}, ensure_ascii=False), encoding="utf-8")


def load_short_memory():
    p = _short_memory_path()
    if not p or not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("content", "")
    except Exception:
        return ""


def save_short_memory(content):
    p = _short_memory_path()
    if not p:
        return
    p.write_text(json.dumps({"content": content}, ensure_ascii=False), encoding="utf-8")


def extract_user_info_sync(message):
    from prompts import USER_INFO_EXTRACT_PROMPT
    from utils.llm_utils import create_llm

    prompt = USER_INFO_EXTRACT_PROMPT.format(message=message)
    try:
        llm = create_llm(temperature=0.1)
        result = llm.invoke(prompt)
        text = result.content if hasattr(result, "content") else str(result)
        text = text.strip()
        if text and text != "无":
            return text
    except Exception as e:
        logger.error(f"[rag/memory] extract_user_info_sync error: {e}")
    return ""


def compress_text_sync(text, prompt_template):
    from utils.llm_utils import create_llm

    prompt = prompt_template.format(content=text)
    try:
        llm = create_llm(temperature=0.1)
        result = llm.invoke(prompt)
        return (result.content if hasattr(result, "content") else str(result)).strip()
    except Exception:
        return text


def update_long_memory(user_message):
    with _LOCK:
        from sidecar.rag.profile import update_profile_from_message
        update_profile_from_message(user_message)

        new_info = extract_user_info_sync(user_message)
        if not new_info:
            return

        current = load_long_memory()
        combined = current + "\n" + new_info if current else new_info

        if len(combined) > _MAX_LONG_MEMORY_CHARS:
            from prompts import LONG_MEMORY_COMPRESS_PROMPT
            combined = compress_text_sync(combined, LONG_MEMORY_COMPRESS_PROMPT)

        save_long_memory(combined)


def update_short_memory(chat_history):
    if not chat_history:
        return

    with _LOCK:
        lines = []
        for msg in chat_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"用户: {content}")
            elif role == "assistant":
                lines.append(f"助手: {content}")
        full_text = "\n".join(lines)

        from prompts import MEMORY_COMPRESS_PROMPT
        compressed = compress_text_sync(full_text, MEMORY_COMPRESS_PROMPT)
        save_short_memory(compressed)


def build_memory_section():
    from sidecar.rag.profile import get_profile_summary
    profile_summary = get_profile_summary()

    long_mem = load_long_memory()
    short_mem = load_short_memory()
    parts = []
    if profile_summary:
        parts.append(f"[用户画像]\n{profile_summary}")
    if long_mem:
        parts.append(f"[关于用户的长期记忆]\n{long_mem}")
    if short_mem:
        parts.append(f"[近期对话摘要]\n{short_mem}")
    if parts:
        return "\n".join(parts) + "\n\n"
    return ""
