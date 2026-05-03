import re
from pathlib import Path

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    jieba = None
    JIEBA_AVAILABLE = False

MIN_TAG_LENGTH = 2
OCCURRENCE_THRESHOLD = 3

GENERIC_WORDS = {
    # 中文泛词 — 出现频率高但不表达主题区分度
    "笔记", "指南", "教程", "总结", "参考", "入门", "实战", "实践",
    "记录", "文档", "资料", "配置", "安装", "使用", "开发", "学习",
    "示例", "范例", "详解", "解析", "介绍", "概览", "概述", "说明",
    "整理", "版本", "更新", "修订", "补充", "合集", "汇总", "索引",
    "目录", "手册", "心得", "经验", "技巧", "方法", "方案", "思路",
    # 英文泛词 — 文档/工具类
    "note", "notes", "guide", "doc", "docs", "tips", "todo",
    "draft", "demo", "api", "ref", "usage", "index", "readme",
    "tutorial", "example", "sample", "quickstart", "overview",
    "summary", "intro", "getting-started", "howto", "cheatsheet",
    "reference", "manual", "handbook", "setup", "config",
    "v1", "v2", "v3", "v4", "v5",
    # 英文泛词 — 常见动词
    "make", "made", "making", "take", "taken", "taking",
    "give", "given", "giving", "come", "came", "coming",
    "go", "going", "gone", "get", "got", "getting",
    "put", "putting", "set", "setting", "run", "running",
    "use", "used", "using", "try", "tried", "trying",
    "need", "needed", "needing", "want", "wanted", "wanting",
    "know", "knew", "known", "think", "thought", "thinking",
    "see", "saw", "seen", "look", "looked", "looking",
    "find", "found", "finding", "give", "gave", "given",
    "tell", "told", "telling", "ask", "asked", "asking",
    "work", "working", "worked", "call", "called", "calling",
    "keep", "kept", "keeping", "let", "letting", "begin",
    "show", "shown", "showing", "hear", "heard", "hearing",
    "play", "played", "playing", "move", "moved", "moving",
    "live", "lived", "living", "believe", "believed",
    "hold", "held", "holding", "bring", "brought", "bringing",
    "happen", "happened", "write", "wrote", "written", "writing",
    "provide", "provided", "providing", "sit", "sat", "sitting",
    "stand", "stood", "standing", "lose", "lost", "losing",
    "pay", "paid", "paying", "meet", "met", "meeting",
    "include", "including", "continue", "continued",
    "learn", "learned", "learning", "change", "changed", "changing",
    "lead", "led", "leading", "understand", "understood",
    "watch", "watched", "watching", "follow", "followed", "following",
    "stop", "stopped", "stopping", "create", "created", "creating",
    "speak", "spoke", "spoken", "read", "reading",
    "allow", "allowed", "allowing", "add", "added", "adding",
    "spend", "spent", "spending", "grow", "grew", "grown",
    "win", "won", "winning", "offer", "offered", "offering",
    "remember", "remembered", "love", "loved", "loving",
    "consider", "considered", "appear", "appeared", "appearing",
    "buy", "bought", "buying", "wait", "waited", "waiting",
    "serve", "served", "serving", "die", "died", "dying",
    "send", "sent", "sending", "expect", "expected", "expecting",
    "build", "built", "building", "stay", "stayed", "staying",
    "fall", "fell", "fallen", "cut", "cutting",
    "reach", "reached", "reaching", "kill", "killed", "killing",
    "remain", "remained", "suggest", "suggested", "suggesting",
    "raise", "raised", "raising", "pass", "passed", "passing",
    "sell", "sold", "selling", "require", "required", "requiring",
    "report", "reported", "reporting", "decide", "decided", "deciding",
    "pull", "pulled", "pulling", "develop", "developed", "developing",
    # 英文泛词 — 常见形容词/副词
    "good", "great", "best", "better", "well", "bad", "worse", "worst",
    "new", "old", "big", "small", "large", "little", "long", "short",
    "high", "low", "tall", "deep", "wide", "narrow", "thick", "thin",
    "fast", "slow", "hard", "easy", "simple", "difficult", "complex",
    "important", "interesting", "possible", "impossible", "necessary",
    "different", "similar", "same", "another", "other", "next",
    "first", "last", "final", "main", "major", "minor",
    "real", "true", "false", "right", "wrong", "free",
    "full", "empty", "whole", "part", "partial",
    "early", "late", "recent", "current", "previous", "local",
    "general", "common", "special", "basic", "standard", "normal",
    "natural", "physical", "social", "public", "private",
    "able", "available", "actual", "original", "certain",
    "sure", "clear", "obvious", "exact", "specific",
    "strong", "weak", "light", "dark", "heavy",
    "hot", "cold", "warm", "cool", "dry", "wet",
    "clean", "dirty", "safe", "dangerous", "quiet", "loud",
    "happy", "sad", "angry", "afraid", "alone", "alive",
    "also", "very", "really", "just", "still", "already",
    "always", "never", "often", "sometimes", "usually",
    "here", "there", "where", "when", "how", "why",
    "now", "then", "today", "tomorrow", "yesterday",
    "again", "away", "back", "down", "up", "out",
    "only", "even", "almost", "enough", "much", "more", "most",
    "less", "least", "quite", "rather", "too",
    # 英文泛词 — 常见名词/代词/介词/连词
    "thing", "things", "way", "ways", "part", "parts",
    "point", "points", "case", "cases", "fact", "facts",
    "time", "times", "day", "days", "year", "years",
    "people", "person", "man", "men", "woman", "women",
    "world", "life", "hand", "hands", "place", "places",
    "group", "groups", "number", "numbers", "area", "areas",
    "end", "ends", "side", "sides", "kind", "kinds",
    "head", "problem", "problems", "question", "questions",
    "idea", "ideas", "reason", "reasons", "result", "results",
    "role", "roles", "value", "values", "level", "levels",
    "name", "names", "type", "types", "form", "forms",
    "source", "sources", "field", "fields", "term", "terms",
    "step", "steps", "process", "processes", "method", "methods",
    "data", "info", "information", "detail", "details",
    "item", "items", "element", "elements", "feature", "features",
    "version", "versions", "update", "updates",
    "the", "this", "that", "these", "those",
    "which", "what", "who", "whom", "whose",
    "each", "every", "all", "some", "any", "no",
    "not", "and", "but", "or", "nor", "for", "yet", "so",
    "with", "from", "into", "about", "between", "through",
    "during", "before", "after", "above", "below",
    "under", "over", "without", "within", "along",
    "against", "upon", "toward", "towards",
    "both", "either", "neither", "whether",
    "while", "because", "although", "though", "unless",
    "until", "since", "once", "than", "as",
    "should", "would", "could", "might", "must", "shall",
    "can", "will", "does", "did", "has", "have", "had",
    "been", "being", "doing", "having",
    "own", "other", "another", "such",
    "one", "two", "three", "four", "five",
    "six", "seven", "eight", "nine", "ten",
    "first", "second", "third", "fourth", "fifth",
    "many", "much", "few", "little", "several",
    "however", "therefore", "thus", "hence", "moreover",
    "furthermore", "nevertheless", "meanwhile", "otherwise",
    "instead", "anyway", "somehow", "somewhat",
    "maybe", "perhaps", "probably", "certainly",
    "usually", "often", "sometimes", "always", "never",
    "already", "still", "yet", "just", "even",
    "really", "actually", "simply", "basically",
    "especially", "particularly", "generally", "mainly",
    "simply", "quite", "rather", "fairly",
    "together", "apart", "around", "across",
    "forward", "backward", "upward", "downward",
    "inside", "outside", "beside", "behind",
    "above", "below", "between", "among",
    "onto", "upon", "within", "throughout",
}


CHINESE_STOPWORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就",
    "不", "人", "都", "一", "一个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "她", "他", "它",
    "们", "这个", "那个", "什么", "怎么", "为什么",
    "哪", "哪里", "谁", "多少", "几", "啊", "吧",
    "呢", "吗", "呀", "哦", "嗯", "哈", "哎", "唉",
    "但是", "如果", "因为", "所以", "虽然", "而且",
    "然而", "不过", "于是", "因此", "并且", "或者",
    "还是", "以及", "及其", "关于", "对于", "为了",
    "由于", "根据", "通过", "随着", "按照", "除了",
    "包括", "进行", "可以", "能够", "需要", "可能",
    "应该", "必须", "一定", "已经", "正在", "将",
    "曾", "让", "给", "把", "被", "使", "从", "向",
    "往", "对", "与", "跟", "同", "及", "等", "等等",
    "之类", "之", "以", "而", "于", "其", "此",
    "该", "本", "每", "各", "某", "另", "其他", "另外",
    "任何", "所有", "全部", "部分", "一些", "许多",
    "很多", "更多", "最", "更", "还", "又", "再",
    "仍", "才", "就", "都", "全", "只", "仅", "单",
    "光", "便", "即", "则", "已", "其实", "实际上",
    "事实上", "当然", "显然", "确实", "的确", "真的",
    "实在", "总之", "总而言之", "简言之", "综上所述",
    "由此可见", "因而", "故而", "从而", "结果", "导致",
    "造成", "引起", "使得", "涉及", "有关", "相关",
    "相应", "相应的", "的话", "来说", "而言", "来看",
    "看来", "这样", "那样", "这么", "那么", "怎么",
    "如何", "怎样", "为何", "因", "既然", "假如", "假设",
    "要是", "倘若", "即使", "纵然", "纵使", "尽管", "虽说",
    "固然", "可是", "却", "而", "但", "只是", "只有",
    "只要", "除非", "否则", "不然", "要不然", "无论",
    "不管", "不论", "任凭", "哪怕", "就算", "就是", "还有",
    "此外", "再者", "同时", "同样", "或是", "抑或",
    "要么", "不是", "与其", "不如", "宁可", "也不",
    "毋宁", "什么的", "即将", "曾经", "过去", "现在",
    "未来", "今天", "明天", "昨天", "前天", "后天",
    "今年", "去年", "明年", "前年", "后年", "每天",
    "每周", "每月", "每年", "每次", "第一", "第二",
    "第三", "首先", "其次", "再次", "最后", "最终",
    "终于", "开始", "结束", "停止", "继续", "开展",
    "实施", "执行", "落实", "完成", "达到", "实现",
    "获得", "取得", "得到", "获取", "接收", "接受",
    "同意", "反对", "支持", "帮助", "协助", "配合",
    "参与", "参加", "加入", "退出", "离开", "进入",
    "出来", "上去", "下来", "过来", "回去", "起来",
    "坐下", "站起", "躺下", "睡觉", "醒来", "吃饭",
    "喝水", "说话", "聊天", "讨论", "商量", "研究",
    "思考", "考虑", "分析", "判断", "决定", "选择",
    "挑选", "比较", "对比", "区别", "不同", "相同",
    "类似", "相似", "一样", "同样", "大概", "大约",
    "也许", "大致", "大体", "基本上", "差不多", "几乎",
    "将近", "接近", "左右", "上下", "前后", "以上", "以下",
    "以内", "以外", "之间", "中间", "之内", "之外",
    "旁边", "附近", "周围", "四周", "到处", "处处", "各处",
    "哪里", "这里", "那里", "这边", "那边", "对面",
    "前面", "后面", "左边", "右边", "上面", "下面",
    "里面", "外面", "里头", "外头", "少数", "整个",
    "整体", "各类", "各项", "每一个", "每一种", "每一类",
    "某一个", "某一种", "某一类", "另一个", "另一种",
    "另一类", "其它", "其余", "剩下",
}


def is_chinese_word(word: str) -> bool:
    """判断是否为中文词汇"""
    return bool(re.search(r'[一-鿿]', word))


def is_english_word(word: str) -> bool:
    """判断是否为英文词汇"""
    return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9]*$', word))


def _split_camel_case(text: str) -> str:
    """将 CamelCase 拆分为空格分隔的单词，用于后续分词
    ClaudeCode → Claude Code
    RAGSystem → RAG System
    """
    result = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    result = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', result)
    return result


def tokenize(text: str) -> list:
    """使用 jieba 对文本进行分词（支持中英文混合）

    Args:
        text: 待分词文本（文件名或任意文本）

    Returns:
        分词后的词汇列表，过滤掉空格和短词
    """
    if not text:
        return []

    text = _split_camel_case(text)

    if JIEBA_AVAILABLE and jieba:
        try:
            tokens = jieba.lcut(text)
            return [t.strip() for t in tokens if t.strip() and len(t.strip()) >= MIN_TAG_LENGTH]
        except Exception:
            pass

    text = re.sub(r'[（(].*?[）)]', '', text)
    parts = re.split(r'[-_\s——·|/\\\[\]【】：:，,。.！!？?、]+', text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) >= MIN_TAG_LENGTH]


def tokenize_filename(filename: str) -> list:
    """对文件名进行分词（去扩展名后分词）"""
    stem = Path(filename).stem
    return tokenize(stem)


def _normalize_for_match(s: str) -> str:
    """去除空格用于模糊匹配（"Claude Code" ↔ "ClaudeCode"）"""
    return re.sub(r'\s+', '', s).lower()


def _count_tag_occurrence(tag: str, filenames: list, case_insensitive: bool = True) -> int:
    """统计 tag 在文件名列表中的出现次数（忽略空格和大小写）"""
    tag_norm = _normalize_for_match(tag)
    if case_insensitive and is_english_word(tag):
        return sum(1 for fn in filenames if tag_norm in _normalize_for_match(fn))
    else:
        return sum(1 for fn in filenames if tag_norm in _normalize_for_match(fn))


def _is_generic_word(word: str) -> bool:
    """检查词是否为泛词（不表达主题区分度）"""
    return word.lower() in GENERIC_WORDS


TOP_COMMON_ENGLISH_WORDS = {
    "a", "an", "the",
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "who", "whom", "whose", "which", "what", "that", "this", "these", "those",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did", "doing", "done",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "and", "but", "or", "nor", "not", "so", "yet", "for",
    "if", "then", "else", "when", "while", "as", "than",
    "because", "since", "although", "though", "unless", "until",
    "of", "in", "to", "with", "at", "by", "from", "on", "up", "out",
    "about", "into", "over", "after", "under", "between", "through",
    "during", "before", "without", "within", "along", "against",
    "among", "around", "across", "behind", "below", "above",
    "beside", "beyond", "toward", "towards", "upon", "onto",
    "off", "down", "near", "past", "upon",
    "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "no", "nor", "only", "own",
    "same", "any", "many", "much", "several", "enough",
    "also", "very", "too", "quite", "rather", "really",
    "just", "still", "already", "even", "only", "almost",
    "never", "always", "often", "sometimes", "usually",
    "here", "there", "where", "how", "why", "when",
    "now", "then", "today", "tomorrow", "yesterday",
    "again", "away", "back", "down", "up", "out",
    "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "first", "second",
    "third", "last", "next", "new", "old", "good", "bad",
    "great", "big", "small", "long", "short", "high", "low",
    "well", "better", "best", "right", "left", "true", "false",
    "say", "said", "go", "went", "gone", "get", "got", "gotten",
    "make", "made", "know", "knew", "known", "think", "thought",
    "take", "took", "taken", "see", "saw", "seen",
    "come", "came", "want", "look", "use", "used", "find", "found",
    "give", "gave", "tell", "told", "work", "call", "try", "ask",
    "need", "feel", "become", "leave", "put", "mean", "keep", "let",
    "begin", "seem", "help", "show", "hear", "play", "run", "move",
    "live", "believe", "hold", "bring", "happen", "write", "provide",
    "sit", "stand", "lose", "pay", "meet", "include", "continue",
    "set", "learn", "change", "lead", "understand", "watch", "follow",
    "stop", "create", "speak", "read", "allow", "add", "spend",
    "grow", "open", "walk", "win", "offer", "remember", "consider",
    "appear", "buy", "wait", "serve", "die", "send", "expect",
    "build", "stay", "fall", "cut", "reach", "kill", "remain",
    "suggest", "raise", "pass", "sell", "require", "report",
    "decide", "pull", "develop",
    "time", "year", "years", "people", "way", "day", "days",
    "man", "men", "woman", "women", "child", "children",
    "world", "life", "hand", "part", "place", "case", "week",
    "company", "system", "program", "question", "work",
    "government", "number", "night", "point", "home", "water",
    "room", "mother", "area", "money", "story", "fact", "month",
    "lot", "right", "study", "book", "eye", "job", "word",
    "business", "issue", "side", "kind", "head", "house",
    "service", "friend", "father", "power", "hour", "game",
    "line", "end", "member", "law", "car", "city", "community",
    "name", "president", "team", "minute", "idea", "body",
    "information", "back", "parent", "face", "others", "level",
    "office", "door", "health", "person", "art", "war", "history",
    "party", "result", "change", "morning", "reason", "research",
    "girl", "guy", "moment", "air", "teacher", "force", "education",
    "foot", "boy", "age", "policy", "process", "music", "market",
    "sense", "thing", "things", "nothing", "everything", "something",
    "anything", "someone", "anyone", "everyone", "nobody",
    "every", "all", "some", "any", "no",
    "much", "little", "lot", "few", "less", "least",
    "able", "free", "full", "sure", "hard", "simple", "clear",
    "different", "important", "possible", "public", "real",
    "whole", "special", "easy", "strong", "common", "general",
    "certain", "main", "major", "basic", "normal", "natural",
    "particular", "current", "local", "social", "physical",
}

def _is_meaningful_tag(tag: str) -> bool:
    """检查 tag 是否足够有意义

    纯中文：> 2 汉字
    纯英文：不在常见英文词列表中（介词/连词/冠词/前500常见词）
    中英混合：> 8 字节 且 ≥ 2 个分词
    """
    if not tag or len(tag) < 2:
        return False
    chinese_chars = re.findall(r'[一-鿿]', tag)
    english_letters = re.findall(r'[a-zA-Z]', tag)
    has_chinese = len(chinese_chars) > 0
    has_english = len(english_letters) > 0
    if has_chinese and has_english:
        byte_len = len(tag.encode('utf-8'))
        token_count = len(tokenize(tag))
        return byte_len > 8 and token_count >= 2
    if has_chinese:
        return len(chinese_chars) > 2
    if has_english:
        return tag.lower() not in TOP_COMMON_ENGLISH_WORDS
    return False
