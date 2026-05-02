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
    # 英文泛词
    "note", "notes", "guide", "doc", "docs", "tips", "todo",
    "draft", "demo", "api", "ref", "usage", "index", "readme",
    "tutorial", "example", "sample", "quickstart", "overview",
    "summary", "intro", "getting-started", "howto", "cheatsheet",
    "reference", "manual", "handbook", "setup", "config",
    "v1", "v2", "v3", "v4", "v5",
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


def tokenize(text: str) -> list:
    """使用 jieba 对文本进行分词（支持中英文混合）

    Args:
        text: 待分词文本（文件名或任意文本）

    Returns:
        分词后的词汇列表，过滤掉空格和短词
    """
    if not text:
        return []

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


def _is_meaningful_tag(tag: str) -> bool:
    """检查 tag 是否足够有意义（英文>4字母 或 中文>2汉字）"""
    if not tag or len(tag) < 2:
        return False
    chinese_chars = re.findall(r'[一-鿿]', tag)
    if len(chinese_chars) > 2:
        return True
    english_letters = re.findall(r'[a-zA-Z]', tag)
    if len(english_letters) > 4:
        return True
    return False
