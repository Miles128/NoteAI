import re
import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

try:
    import yaml
    PYYAML_AVAILABLE = True
except ImportError:
    yaml = None
    PYYAML_AVAILABLE = False

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    jieba = None
    JIEBA_AVAILABLE = False

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

MIN_TAG_LENGTH = 2
OCCURRENCE_THRESHOLD = 3


def is_chinese_word(word: str) -> bool:
    """判断是否为中文词汇"""
    return bool(re.search(r'[\u4e00-\u9fff]', word))


def is_english_word(word: str) -> bool:
    """判断是否为英文词汇"""
    return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9]*$', word))


def tokenize_filename(filename: str) -> List[str]:
    """使用 jieba 对文件名进行分词（支持中英文混合）
    
    Args:
        filename: 文件名（可带或不带扩展名）
    
    Returns:
        分词后的词汇列表，过滤掉空格和单个字符
    """
    stem = Path(filename).stem
    
    if JIEBA_AVAILABLE and jieba:
        try:
            tokens = jieba.lcut(stem)
            return [t.strip() for t in tokens if t.strip() and len(t.strip()) >= MIN_TAG_LENGTH]
        except Exception:
            pass
    
    stem = re.sub(r'[（(].*?[）)]', '', stem)
    parts = re.split(r'[-_\s——·|/\\\[\]【】：:，,。.！!？?、]+', stem)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) >= MIN_TAG_LENGTH]


def _collect_workspace_md_filenames(workspace_path: str) -> List[str]:
    """收集 Notes、Organized、Used 文件夹中所有 MD 文件的文件名（只读文件名，不读内容）
    
    Args:
        workspace_path: 工作区根路径
    
    Returns:
        所有 md 文件的文件名列表（不含路径）
    """
    workspace = Path(workspace_path)
    filenames = []
    
    for folder_name in ['Notes', 'Organized', 'Used']:
        folder = workspace / folder_name
        if not folder.exists():
            continue
        md_files = [f for f in folder.rglob('*.md') if not f.name.startswith('.')]
        for md_file in md_files:
            filenames.append(md_file.name)
    
    return filenames


def _count_tag_occurrence(tag: str, filenames: List[str], case_insensitive: bool = True) -> int:
    """统计 tag 在文件名列表中的出现次数
    
    Args:
        tag: 待搜索的标签
        filenames: 文件名列表
        case_insensitive: 是否忽略大小写（仅对英文生效）
    
    Returns:
        出现次数
    """
    if case_insensitive and is_english_word(tag):
        tag_lower = tag.lower()
        return sum(1 for fn in filenames if tag_lower in fn.lower())
    else:
        return sum(1 for fn in filenames if tag in fn)


def _generate_english_pairs(english_words: List[str]) -> List[str]:
    """生成相邻英文单词的组合
    
    例如: ["Machine", "Learning"] -> ["MachineLearning", "Machine Learning"]
    """
    pairs = []
    for i in range(len(english_words) - 1):
        word1 = english_words[i]
        word2 = english_words[i + 1]
        pairs.append(word1 + word2)
        pairs.append(word1 + " " + word2)
        pairs.append(word1 + "-" + word2)
        pairs.append(word1 + "_" + word2)
    return pairs


def _is_word_in_accepted_pair(word: str, accepted_pairs: List[str], case_insensitive: bool = True) -> bool:
    """检查单词是否已被包含在已接受的双词组合中
    
    例如: "Machine" 在 "MachineLearning" 中则返回 True
    """
    if case_insensitive:
        word_lower = word.lower()
        for pair in accepted_pairs:
            if word_lower in pair.lower():
                return True
    else:
        for pair in accepted_pairs:
            if word in pair:
                return True
    return False


def extract_tags_from_filename(file_path: str) -> List[str]:
    """基于文件名分词提取标签
    
    算法：
    1. 使用 jieba 对当前文件的文件名进行分词
    2. 按优先级处理：
       a. 英文双词组合：相邻英文单词组合，在文件名中出现次数 > 3 则加入
       b. 英文单词：单个英文单词，若未被包含在已接受的双词组合中，且出现次数 > 3 则加入
       c. 中文单词：排除中文停用词，出现次数 > 3 则加入
    3. 只对比文件名，不读取文件内容
    
    Args:
        file_path: 待打标签的文件路径
    
    Returns:
        标签字符串列表
    """
    from config.settings import config
    
    if not config.workspace_path:
        return []
    
    file_path_obj = Path(file_path)
    
    tokens = tokenize_filename(file_path_obj.name)
    
    if not tokens:
        return []
    
    workspace_filenames = _collect_workspace_md_filenames(config.workspace_path)
    
    if not workspace_filenames:
        return []
    
    english_words = []
    chinese_words = []
    
    for token in tokens:
        if is_english_word(token):
            english_words.append(token)
        elif is_chinese_word(token):
            chinese_words.append(token)
    
    tags = []
    accepted_english_pairs = []
    
    if len(english_words) >= 2:
        pairs = _generate_english_pairs(english_words)
        seen_pairs = set()
        for pair in pairs:
            if pair.lower() in seen_pairs:
                continue
            seen_pairs.add(pair.lower())
            count = _count_tag_occurrence(pair, workspace_filenames)
            if count > OCCURRENCE_THRESHOLD:
                tags.append(pair)
                accepted_english_pairs.append(pair)
    
    for word in english_words:
        if _is_word_in_accepted_pair(word, accepted_english_pairs):
            continue
        count = _count_tag_occurrence(word, workspace_filenames)
        if count > OCCURRENCE_THRESHOLD:
            tags.append(word)
    
    for word in chinese_words:
        if word in CHINESE_STOPWORDS:
            continue
        count = _count_tag_occurrence(word, workspace_filenames)
        if count > OCCURRENCE_THRESHOLD:
            tags.append(word)
    
    seen = set()
    unique_tags = []
    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            seen.add(tag_lower)
            unique_tags.append(tag)
    
    return unique_tags


def tag_files_by_filename(file_paths: List[str]) -> Dict[str, List[str]]:
    """对一批 Markdown 文件基于文件名分词提取标签并添加 YAML front matter
    
    Args:
        file_paths: Markdown 文件路径列表
    
    Returns:
        {文件路径: 标签列表} 字典
    """
    if not file_paths:
        return {}
    
    results = {}
    for fp in file_paths:
        try:
            tags = extract_tags_from_filename(fp)
            if tags:
                add_yaml_frontmatter_to_file(fp, tags=tags)
                results[fp] = tags
        except Exception:
            continue
    
    return results


def _parse_yaml_value_simple(value: str) -> Any:
    """简单的 YAML 值解析器（fallback，用于没有 PyYAML 时）"""
    value = value.strip()
    
    if not value:
        return None
    
    if value.startswith('[') and value.endswith(']'):
        list_content = value[1:-1].strip()
        if not list_content:
            return []
        items = []
        current = ""
        in_quotes = None
        i = 0
        while i < len(list_content):
            c = list_content[i]
            if c in ['"', "'"]:
                if in_quotes == c:
                    in_quotes = None
                elif in_quotes is None:
                    in_quotes = c
                else:
                    current += c
            elif c == ',' and in_quotes is None:
                items.append(current.strip())
                current = ""
            else:
                current += c
            i += 1
        if current:
            items.append(current.strip())
        result = []
        for item in items:
            item = item.strip()
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            elif item.startswith("'") and item.endswith("'"):
                item = item[1:-1].replace("\\'", "'").replace('\\\\', '\\')
            result.append(item)
        return result
    
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("\\'", "'").replace('\\\\', '\\')
    
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False
    if value.lower() == 'null':
        return None
    
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    
    return value


def _parse_yaml_frontmatter_simple(content: str) -> Dict[str, Any]:
    """简单的 YAML front matter 解析器（fallback）"""
    result = {}
    lines = content.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            if key:
                result[key] = _parse_yaml_value_simple(value)
    
    return result


def _escape_yaml_string(value: str) -> str:
    """转义YAML字符串中的特殊字符"""
    if not value:
        return '""'
    
    needs_quoting = False
    special_chars = ['"', '\\', '\n', '\r', '\t', '#', ': ', '[', ']', '{', '}', ',', '*', '&', '!', '|', '>', '%', '@', '`']
    
    for char in special_chars:
        if char in value:
            needs_quoting = True
            break
    
    if value.startswith((' ', '-', '?', ':')) or value.endswith(' '):
        needs_quoting = True
    
    if not needs_quoting:
        return value
    
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('\t', '\\t')
    
    return f'"{value}"'


def _format_yaml_value(value: Any) -> str:
    """格式化YAML值，根据类型选择合适的表示方式"""
    if value is None:
        return 'null'
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        if not value:
            return '[]'
        items = ', '.join(_escape_yaml_string(str(item)) for item in value)
        return f'[{items}]'
    elif isinstance(value, datetime):
        return _escape_yaml_string(value.strftime('%Y-%m-%d'))
    else:
        return _escape_yaml_string(str(value))


def generate_yaml_frontmatter(
    title: str = "",
    tags: List[str] = None,
    date: datetime = None,
    source: str = "",
    extra_fields: Dict[str, Any] = None
) -> str:
    """生成标准的 YAML front matter（仅包含 tags 和 source）
    
    参数：
        title: 文档标题
        tags: 标签列表
        date: 创建/处理日期（默认当前日期）
        source: 来源（URL或文件路径）
        extra_fields: 额外的自定义字段
    
    返回：
        完整的 YAML front matter 字符串（包含 --- 分隔符）
    """
    fields = {}
    
    if title:
        fields['title'] = title
    
    if tags:
        fields['tags'] = tags
    else:
        fields['tags'] = []
    
    if date is None:
        date = datetime.now()
    fields['date'] = date
    
    if source:
        fields['source'] = source
    
    if extra_fields:
        fields.update(extra_fields)
    
    lines = ['---']
    
    ordered_keys = ['title', 'tags', 'date', 'source']
    for key in ordered_keys:
        if key in fields:
            value = fields.pop(key)
            lines.append(f"{key}: {_format_yaml_value(value)}")
    
    for key, value in sorted(fields.items()):
        lines.append(f"{key}: {_format_yaml_value(value)}")
    
    lines.append('---')
    lines.append('')
    
    return '\n'.join(lines)


def parse_yaml_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """解析 Markdown 文件中的 YAML front matter
    
    参数：
        content: Markdown 文件完整内容
    
    返回：
        (frontmatter_dict, remaining_content)
    """
    frontmatter = {}
    body = content
    
    if not content.startswith('---\n'):
        return frontmatter, body
    
    lines = content.split('\n')
    frontmatter_lines = []
    frontmatter_end_index = None
    
    for i, line in enumerate(lines[1:], start=1):
        if line == '---':
            frontmatter_end_index = i
            break
        frontmatter_lines.append(line)
    
    if frontmatter_end_index is None:
        return frontmatter, body
    
    frontmatter_content = '\n'.join(frontmatter_lines)
    if frontmatter_content.strip():
        try:
            if PYYAML_AVAILABLE and yaml is not None:
                frontmatter = yaml.safe_load(frontmatter_content) or {}
            else:
                frontmatter = _parse_yaml_frontmatter_simple(frontmatter_content)
        except Exception:
            frontmatter = {}
    
    remaining_lines = lines[frontmatter_end_index + 1:]
    while remaining_lines and remaining_lines[0].strip() == '':
        remaining_lines.pop(0)
    body = '\n'.join(remaining_lines)
    
    return frontmatter, body


def add_yaml_frontmatter_to_content(
    content: str,
    title: str = "",
    tags: List[str] = None,
    source: str = "",
    extra_fields: Dict[str, Any] = None
) -> str:
    """为 Markdown 内容添加 YAML front matter
    
    如果内容已存在 front matter，则更新它；否则添加新的。
    
    参数：
        content: 原始 Markdown 内容
        title: 文档标题（如未提供，尝试从内容中提取）
        tags: 标签列表
        source: 来源（URL或文件路径）
        extra_fields: 额外字段
    
    返回：
        添加了 front matter 的完整内容
    """
    existing_frontmatter, body = parse_yaml_frontmatter(content)
    
    if not title:
        title_match = re.match(r'^#\s+(.+)$', body.lstrip(), re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
    
    if tags is None:
        tags = []
    
    new_frontmatter = generate_yaml_frontmatter(
        title=title,
        tags=tags,
        source=source,
        extra_fields=extra_fields
    )
    
    return new_frontmatter + body


def add_yaml_frontmatter_to_file(
    file_path: str,
    title: str = "",
    tags: List[str] = None,
    source: str = "",
    extra_fields: Dict[str, Any] = None
) -> bool:
    """为 Markdown 文件添加 YAML front matter
    
    参数：
        file_path: Markdown 文件路径
        title: 文档标题
        tags: 标签列表
        source: 来源
        extra_fields: 额外字段
    
    返回：
        是否成功
    """
    p = Path(file_path)
    if not p.exists() or not p.suffix.lower() == '.md':
        return False
    
    try:
        content = p.read_text(encoding='utf-8')
        new_content = add_yaml_frontmatter_to_content(
            content,
            title=title,
            tags=tags,
            source=source,
            extra_fields=extra_fields
        )
        p.write_text(new_content, encoding='utf-8')
        return True
    except Exception:
        return False


def process_and_tag_file_with_yaml(
    file_path: str,
    source: str = "",
    title: str = ""
) -> Dict[str, Any]:
    """处理单个文件，基于文件名分词提取标签并添加 YAML front matter
    
    参数：
        file_path: Markdown 文件路径
        source: 来源信息（URL或原文件路径）
        title: 可选的标题覆盖
    
    返回：
        包含处理结果的字典：{'success': bool, 'tags': list, 'title': str}
    """
    result = {
        'success': False,
        'tags': [],
        'title': title,
    }
    
    p = Path(file_path)
    if not p.exists() or not p.suffix.lower() == '.md':
        return result
    
    try:
        content = p.read_text(encoding='utf-8')
        
        existing_frontmatter, body = parse_yaml_frontmatter(content)
        
        if not title:
            title = existing_frontmatter.get('title', '')
            if not title:
                from utils.helpers import extract_title_from_markdown
                title = extract_title_from_markdown(body) or p.stem
        
        tags = extract_tags_from_filename(file_path)
        
        new_frontmatter = generate_yaml_frontmatter(
            title=title,
            tags=tags,
            source=source,
        )
        
        new_content = new_frontmatter + body
        p.write_text(new_content, encoding='utf-8')
        
        result['success'] = True
        result['tags'] = tags
        result['title'] = title
        
        return result
    except Exception:
        return result
