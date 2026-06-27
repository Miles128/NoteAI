from config.constants import TOPIC_SEP
from config.settings import config
from utils.logger import logger
from utils.text_utils import _is_generic_word, _is_meaningful_tag, _normalize_for_match
from utils.text_utils import tokenize as tokenize_text


def _norm_topic(topic: str) -> str:
    clean = topic.strip()
    if "/" in clean and TOPIC_SEP not in clean:
        clean = clean.replace("/", TOPIC_SEP)
    return clean


def _find_best_topic_match(hint: str, headings: list) -> str:
    hint_norm = _normalize_for_match(hint)
    hint_tokens = tokenize_text(hint)

    for h in headings:
        if _normalize_for_match(h["name"]) == hint_norm:
            return h["name"]

    for h in headings:
        name_norm = _normalize_for_match(h["name"])
        if hint_norm in name_norm or name_norm in hint_norm:
            return h["name"]

    best_score = 0
    best_topic = None
    for h in headings:
        topic_tokens = tokenize_text(h["name"])
        score = 0
        for ht in hint_tokens:
            if _is_meaningful_tag(ht):
                for tt in topic_tokens:
                    if _normalize_for_match(ht) == _normalize_for_match(tt):
                        score += 2
        if _has_consecutive_two_words_match(topic_tokens, hint):
            score += 3
        if _has_consecutive_two_words_match(hint_tokens, h["name"]):
            score += 3
        if score > best_score:
            best_score = score
            best_topic = h["name"]

    if best_topic and best_score >= 2:
        return best_topic

    return None


def _has_consecutive_two_words_match(topic_tokens: list, filename: str) -> bool:
    filename_norm = _normalize_for_match(filename)

    for i in range(len(topic_tokens) - 1):
        word1 = topic_tokens[i]
        word2 = topic_tokens[i + 1]
        combined = _normalize_for_match(word1 + word2)
        if combined in filename_norm:
            return True

    return False


def _has_meaningful_word_match(word: str, topic_name: str) -> bool:
    if not _is_meaningful_tag(word):
        return False

    return _normalize_for_match(word) in _normalize_for_match(topic_name)


def _llm_suggest_topic(title, tags, content_preview, topic_names):
    if not config.api_key:
        return []
    if not topic_names:
        return []

    from prompts import TOPIC_SUGGESTION_PROMPT
    from utils.llm_utils import call_llm

    tags_str = ", ".join(tags) if tags else "无"
    topic_list_str = "\n".join(f"- {t}" for t in topic_names)

    prompt = TOPIC_SUGGESTION_PROMPT.format(title=title, tags=tags_str)

    prompt += f"\n\n已有的主题分类列表（请优先从中选择）：\n{topic_list_str}"

    prompt += f"\n\n文章内容预览：\n{content_preview}"

    try:
        from sidecar.workspace_rules import format_wiki_topic_structure_for_llm

        prompt += "\n\n" + format_wiki_topic_structure_for_llm(800)
    except Exception:
        pass

    try:
        result = call_llm(prompt, temperature=0.3)
        suggested = []
        for line in result.strip().split("\n"):
            line = line.strip().lstrip("-•*0-9. ").strip()
            if not line:
                continue
            for tn in topic_names:
                if _normalize_for_match(line) == _normalize_for_match(tn):
                    suggested.append(tn)
                    break
            else:
                if line and len(line) <= 20:
                    suggested.append(line)
        return suggested[:4]
    except Exception as e:
        logger.error(f"[llm_suggest_topic] failed: {e}")
        return []


def _collect_topic_candidates(headings, filename: str, tags: list[str]):
    high_priority_candidates = []
    low_priority_candidates = []
    normalized_filename = _normalize_for_match(filename)

    for heading in headings:
        h_name = heading["name"]
        topic_tokens = tokenize_text(h_name)
        if _has_consecutive_two_words_match(topic_tokens, filename):
            high_priority_candidates.append(heading)
            continue
        if any(_has_meaningful_word_match(tag, h_name) for tag in tags):
            if heading not in low_priority_candidates:
                low_priority_candidates.append(heading)
            continue
        for token in topic_tokens:
            if _is_meaningful_tag(token) and _normalize_for_match(token) in normalized_filename:
                if heading not in low_priority_candidates and heading not in high_priority_candidates:
                    low_priority_candidates.append(heading)
                break

    candidates = [h["name"] for h in high_priority_candidates]
    extra_candidates = [h["name"] for h in low_priority_candidates if h["name"] not in candidates]
    for raw in [*tags, *tokenize_text(filename)]:
        if (
            _is_meaningful_tag(raw)
            and not _is_generic_word(raw)
            and raw not in candidates
            and raw not in extra_candidates
        ):
            extra_candidates.append(raw)
    return high_priority_candidates, candidates, extra_candidates


def _match_llm_suggestions(llm_suggestions, headings):
    matched = []
    for suggestion in llm_suggestions:
        for heading in headings:
            if _normalize_for_match(suggestion) == _normalize_for_match(heading["name"]):
                matched.append(heading["name"])
                break
    return matched
