import json
import sys
import threading
from datetime import datetime
from pathlib import Path

from config import config

_LOCK = threading.Lock()

_DEFAULT_PROFILE = {
    "identity": {
        "profession": "",
        "expertise_areas": [],
        "interests": [],
        "learning_goals": [],
    },
    "preferences": {
        "answer_style": "concise",
        "detail_level": "technical",
    },
    "behavior": {
        "frequent_topics": [],
    },
    "raw_facts": [],
    "profile_md": "",
    "last_updated": "",
}


def _profile_path() -> Path | None:
    ws = config.workspace_path
    if not ws:
        return None
    d = Path(ws) / ".ai_memory"
    d.mkdir(exist_ok=True)
    return d / "user_profile.json"


def load_profile() -> dict:
    p = _profile_path()
    if not p or not p.exists():
        return json.loads(json.dumps(_DEFAULT_PROFILE))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        for key in _DEFAULT_PROFILE:
            if key not in data:
                data[key] = _DEFAULT_PROFILE[key]
            elif isinstance(_DEFAULT_PROFILE[key], dict):
                for sub_key in _DEFAULT_PROFILE[key]:
                    if sub_key not in data[key]:
                        data[key][sub_key] = _DEFAULT_PROFILE[key][sub_key]
        return data
    except Exception:
        return json.loads(json.dumps(_DEFAULT_PROFILE))


def save_profile(profile: dict):
    p = _profile_path()
    if not p:
        return
    profile["last_updated"] = datetime.now().isoformat()
    p.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_structured_info(message: str) -> dict | None:
    from utils.llm_utils import create_llm
    from prompts.profile import PROFILE_EXTRACT_PROMPT

    prompt = PROFILE_EXTRACT_PROMPT.format(message=message)
    try:
        llm = create_llm(temperature=0.1)
        result = llm.invoke(prompt)
        text = result.content if hasattr(result, "content") else str(result)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        return data
    except Exception as e:
        sys.stderr.write(f"[profile] extract_structured_info error: {e}\n")
        sys.stderr.flush()
        return None


def update_profile_from_message(user_message: str):
    with _LOCK:
        info = extract_structured_info(user_message)
        if not info:
            return

        profile = load_profile()
        changed = False

        identity = profile.get("identity", {})
        if info.get("profession"):
            identity["profession"] = info["profession"]
            changed = True
        if info.get("expertise_areas"):
            existing = set(identity.get("expertise_areas", []))
            identity["expertise_areas"] = list(existing | set(info["expertise_areas"]))
            changed = True
        if info.get("interests"):
            existing = set(identity.get("interests", []))
            identity["interests"] = list(existing | set(info["interests"]))
            changed = True
        if info.get("learning_goals"):
            existing = set(identity.get("learning_goals", []))
            identity["learning_goals"] = list(existing | set(info["learning_goals"]))
            changed = True
        profile["identity"] = identity

        if info.get("facts"):
            raw_facts = profile.get("raw_facts", [])
            raw_facts.extend(info["facts"])
            profile["raw_facts"] = raw_facts[-50:]
            changed = True

        if changed:
            save_profile(profile)


def update_profile_from_topics(topic_list: list[str]):
    with _LOCK:
        profile = load_profile()
        profile["behavior"]["frequent_topics"] = topic_list[:20]
        save_profile(profile)


def get_profile_summary() -> str:
    profile = load_profile()
    profile_md = profile.get("profile_md", "").strip()
    if profile_md:
        topics = profile.get("behavior", {}).get("frequent_topics", [])
        if topics:
            return profile_md + f"\n近期关注主题：{', '.join(topics[:5])}"
        return profile_md

    identity = profile.get("identity", {})
    profession = identity.get("profession", "")
    expertise = identity.get("expertise_areas", [])
    interests = identity.get("interests", [])
    goals = identity.get("learning_goals", [])
    topics = profile.get("behavior", {}).get("frequent_topics", [])
    prefs = profile.get("preferences", {})
    style = prefs.get("answer_style", "concise")
    detail = prefs.get("detail_level", "technical")

    parts = []
    if profession:
        parts.append(f"职业：{profession}")
    if expertise:
        parts.append(f"专业领域：{', '.join(expertise)}")
    if interests:
        parts.append(f"兴趣：{', '.join(interests)}")
    if goals:
        parts.append(f"学习目标：{', '.join(goals)}")
    if topics:
        parts.append(f"近期关注主题：{', '.join(topics[:5])}")
    parts.append(f"偏好：{style}风格、{detail}深度")

    return "；".join(parts) if parts else ""


def rewrite_query_with_profile(query: str) -> str:
    summary = get_profile_summary()
    if not summary:
        return query

    interests = load_profile().get("identity", {}).get("interests", [])
    topics = load_profile().get("behavior", {}).get("frequent_topics", [])

    context_hints = interests + topics
    if not context_hints:
        return query

    hints_str = "、".join(context_hints[:5])
    return f"{query}（用户关注领域：{hints_str}）"
