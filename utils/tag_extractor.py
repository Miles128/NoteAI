import re
import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Optional, Any, Tuple
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

try:
    import yaml
    PYYAML_AVAILABLE = True
except ImportError:
    yaml = None
    PYYAML_AVAILABLE = False


STOPWORDS: Set[str] = {
    '的', '了', '是', '在', '和', '与', '或', '以及', '等', '之', '于',
    '上', '下', '中', '为', '与', '其', '所', '以', '因', '对', '将',
    '可', '能', '会', '有', '也', '都', '而', '着', '到', '这', '那',
    '个', '一', '不', '就', '但', '又', '被', '从', '由', '向', '往',
    '如', '把', '让', '给', '用', '通过', '根据', '按照', '为了',
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
    'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
    'it', 'its', 'not', 'no', 'so', 'if', 'then', 'than',
    '步骤', '功能', '方法', '使用', '介绍', '说明', '指南', '教程',
    '文档', '文件', '笔记', '记录', '总结', '概述', '简介', '说明',
    '实现', '开发', '测试', '运行', '启动', '停止', '结束', '开始',
    '配置', '设置', '参数', '选项', '模式', '状态', '结果', '输出',
    '输入', '处理', '分析', '计算', '生成', '创建', '删除', '修改',
    '更新', '保存', '加载', '读取', '写入', '导入', '导出', '转换',
    '比较', '判断', '条件', '循环', '遍历', '搜索', '查找', '过滤',
    '排序', '分组', '合并', '拆分', '复制', '移动', '链接', '引用',
    '问题', '错误', '异常', '警告', '提示', '信息', '调试', '日志',
    '成功', '失败', '完成', '未完成', '待办', '进行中', '已完成',
    '简单', '复杂', '基础', '高级', '进阶', '入门', '精通', '实战',
    '完整', '部分', '全部', '部分', '详细', '简要', '详细说明',
    '快速', '慢速', '自动', '手动', '智能', '简单', '方便', '实用',
    '重要', '主要', '次要', '关键', '核心', '基本', '常见', '特殊',
    '普通', '一般', '标准', '自定义', '默认', '可选', '必需',
    '第一', '第二', '第三', '最后', '最终', '初始', '临时', '永久',
    '本地', '远程', '线上', '线下', '内部', '外部', '公开', '私有',
    '项目', '模块', '组件', '类', '函数', '方法', '属性', '变量',
    '常量', '接口', '协议', '服务', '客户端', '服务端', '数据库',
    '缓存', '队列', '线程', '进程', '任务', '作业', '计划', '定时',
    '实时', '延迟', '同步', '异步', '并行', '串行', '批量', '单个',
    '多个', '单个', '全部', '部分', '整体', '局部', '全局',
    '什么', '怎么', '如何', '为什么', '何时', '何地', '哪些', '哪个',
    '关于', '对于', '至于', '由于', '因此', '所以', '因为', '所以',
    '但是', '然而', '不过', '虽然', '尽管', '即使', '如果', '除非',
    '只要', '只有', '除非', '否则', '此外', '另外', '同时', '并且',
    '或者', '还是', '要么', '以及', '还有', '包括', '包含', '除了',
    '之外', '之内', '之外', '之间', '之中', '之内', '之间',
    'new', 'old', 'create', 'delete', 'update', 'read', 'write',
    'get', 'set', 'add', 'remove', 'start', 'stop', 'run', 'test',
    'build', 'deploy', 'config', 'setting', 'option', 'param', 'mode',
    'status', 'result', 'error', 'warning', 'info', 'debug', 'log',
    'success', 'fail', 'done', 'todo', 'doing', 'simple', 'complex',
    'basic', 'advanced', 'quick', 'slow', 'auto', 'manual', 'smart',
    'easy', 'hard', 'important', 'main', 'key', 'core', 'common',
    'special', 'normal', 'standard', 'custom', 'default', 'optional',
    'required', 'first', 'second', 'third', 'last', 'final', 'init',
    'temp', 'perm', 'local', 'remote', 'online', 'offline', 'internal',
    'external', 'public', 'private', 'project', 'module', 'component',
    'class', 'function', 'method', 'attribute', 'var', 'variable', 'const',
    'constant', 'interface', 'protocol', 'service', 'client', 'server',
    'db', 'database', 'cache', 'queue', 'thread', 'process', 'task',
    'job', 'schedule', 'cron', 'real', 'time', 'delay', 'sync', 'async',
    'parallel', 'serial', 'batch', 'single', 'multi', 'all', 'part',
    'whole', 'global', 'intro', 'guide', 'tutorial', 'doc', 'document',
    'note', 'record', 'summary', 'overview', 'implement', 'develop'
}

MIN_WORD_LEN = 2
MAX_TAGS = 5
MIN_TAGS = 0
MIN_TF_IDF_SCORE = 0.01
MIN_DOC_FREQ_PERCENT = 0.05
MIN_DOC_FREQ_COUNT = 3


def _parse_yaml_value_simple(value: str) -> Any:
    """
    简单的 YAML 值解析器（fallback，用于没有 PyYAML 时）。
    支持基本类型：字符串、数字、布尔值、列表。
    """
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
    """
    简单的 YAML front matter 解析器（fallback）。
    只支持基本的 key: value 格式，用于没有 PyYAML 时。
    """
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


def tokenize(text: str) -> List[str]:
    """中英文混合分词"""
    text = text.lower()
    words = []
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
    english_pattern = re.compile(r'[a-z]+')
    other = re.compile(r'[^\w]')

    pos = 0
    while pos < len(text):
        m = chinese_pattern.match(text, pos)
        if m:
            chinese_text = m.group()
            if len(chinese_text) >= 2:
                words.append(chinese_text)
            else:
                words.extend(list(chinese_text))
            pos = m.end()
            continue
        m = english_pattern.match(text, pos)
        if m:
            words.append(m.group())
            pos = m.end()
            continue
        m = other.match(text, pos)
        if m:
            pos = m.end()
            continue
        words.append(text[pos])
        pos += 1

    result = []
    for w in words:
        if w in STOPWORDS:
            continue
        if re.match(r'[\u4e00-\u9fff]+', w):
            if len(w) >= 1:
                result.append(w)
        else:
            if len(w) >= MIN_WORD_LEN:
                result.append(w)
    return result


def compute_tf(tokens: List[str]) -> Dict[str, float]:
    """计算词频 TF"""
    if not tokens:
        return {}
    freq = defaultdict(int)
    for t in tokens:
        freq[t] += 1
    total = len(tokens)
    return {t: count / total for t, count in freq.items()}


def compute_idf(documents: List[List[str]]) -> Dict[str, float]:
    """计算逆文档频率 IDF"""
    df = defaultdict(int)
    for tokens in documents:
        unique = set(tokens)
        for t in unique:
            df[t] += 1
    n = len(documents)
    return {t: math.log((n + 1) / (df[t] + 1)) for t in df}


def compute_tfidf(tf: Dict[str, float], idf: Dict[str, float]) -> Dict[str, float]:
    """计算 TF-IDF"""
    return {t: tf_val * idf.get(t, 0) for t, tf_val in tf.items()}


def extract_tags_from_text(text: str, idf: Dict[str, float] = None) -> List[str]:
    """从单篇文本提取标签"""
    tokens = tokenize(text)
    if not tokens:
        return []
    tf = compute_tf(tokens)
    
    if idf is None:
        sorted_terms = sorted(tf.items(), key=lambda x: x[1], reverse=True)
        tags = [term for term, score in sorted_terms][:MAX_TAGS]
    else:
        tfidf = compute_tfidf(tf, idf)
        sorted_terms = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)
        tags = [term for term, score in sorted_terms if score >= MIN_TF_IDF_SCORE][:MAX_TAGS]
    
    return tags


def extract_tags_batch(
    texts: List[str],
    titles: List[str] = None,
    filenames: List[str] = None,
    n_workers: int = 4
) -> List[List[str]]:
    """
    批量提取多篇文档的标签（并行）。

    参数：
        texts: 文档文本列表，每项对应一篇文档
        titles: 文档标题列表（可选），与 texts 同索引
        filenames: 文件名列表（可选），用于从文件名中提取标签
        n_workers: 并行工作线程数，默认 4

    返回：
        二维列表，外层索引对应文档，内层为该文档的标签列表

    实现说明：
        - 基于 TF-IDF 算法，先对所有文档统一计算 IDF 值，再逐篇计算 TF-IDF
        - 支持从标题和文件名中补充提取标签（权重叠加后去重）
        - 使用 ThreadPoolExecutor 并行处理，提升大批量文档的处理速度

    未使用说明：
        当前项目中使用的是 process_and_tag_file（单文件串行），
        本函数设计用于需要一次性处理大量文档并需要并行加速的场景。
        保留以备未来批量处理需求。
    """
    if not texts:
        return [[] for _ in texts]

    all_tokens = [tokenize(t) for t in texts]
    idf = compute_idf(all_tokens)

    def process_one(idx: int) -> List[str]:
        tokens = all_tokens[idx]
        tf = compute_tf(tokens)
        tfidf = compute_tfidf(tf, idf)
        sorted_terms = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)
        tags = [term for term, score in sorted_terms if score >= MIN_TF_IDF_SCORE][:MAX_TAGS]

        title_extra = []
        if titles and idx < len(titles):
            title_extra = extract_tags_from_text(titles[idx], idf)

        filename_extra = []
        if filenames and idx < len(filenames):
            filename_extra = extract_tags_from_text(filenames[idx], idf)

        all_tags = tags + title_extra + filename_extra
        seen = set()
        unique_tags = []
        for tag in all_tags:
            if tag not in seen and len(unique_tags) < MAX_TAGS:
                seen.add(tag)
                unique_tags.append(tag)
        return unique_tags

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        results = list(executor.map(process_one, range(len(texts))))
    return results


def append_tags_to_markdown(file_path: str, tags: List[str]):
    """
    将标签追加到 Markdown 文件末尾。

    参数：
        file_path: Markdown 文件路径
        tags: 标签列表

    实现说明：
        - 在文件末尾追加 `*标签: tag1, tag2, ...*` 格式行
        - 若文件中已存在标签行，则替换旧标签而非追加
        - 使用 `---` 分隔符与正文区分

    未使用说明：
        当前项目中 process_and_tag_file 函数直接修改文件内容添加标签，
        未调用本函数。本函数适用于需要将标签追加到文件末尾的独立工具场景。
        保留以备未来工具化使用。
    """
    if not tags:
        return
    p = Path(file_path)
    if not p.exists():
        return
    content = p.read_text(encoding='utf-8')
    tag_line = '\n\n---\n*标签: ' + ', '.join(tags) + '*\n'
    if '*标签:' in content:
        existing_tag_pattern = re.compile(r'\*标签:.*?\*\n?', re.DOTALL)
        content = existing_tag_pattern.sub(tag_line.strip(), content)
    else:
        content += tag_line
    p.write_text(content, encoding='utf-8')


def get_workspace_md_files() -> List[Path]:
    """获取工作区中所有 Markdown 文件
    
    Returns:
        MD 文件路径列表，如果没有设置工作区则返回空列表
    """
    try:
        from config.settings import config
        workspace_path = config.workspace_path
        if not workspace_path:
            return []
        workspace = Path(workspace_path)
        if not workspace.exists():
            return []
        return list(workspace.rglob("*.md"))
    except Exception:
        return []


def get_notes_folder_md_files() -> List[Path]:
    """获取工作区中 Notes 目录下的所有 Markdown 文件
    
    Returns:
        Notes 目录下的 MD 文件路径列表
    """
    try:
        from config.settings import config, NOTES_FOLDER
        workspace_path = config.workspace_path
        if not workspace_path:
            return []
        workspace = Path(workspace_path)
        if not workspace.exists():
            return []
        notes_folder = workspace / NOTES_FOLDER
        if not notes_folder.exists():
            return []
        return list(notes_folder.rglob("*.md"))
    except Exception:
        return []


def extract_keywords_from_filename(filename: str) -> List[str]:
    """从文件名中提取关键词
    
    Args:
        filename: 文件名（可以是完整路径或仅文件名）
    
    Returns:
        关键词列表
    """
    if not filename:
        return []
    
    stem = Path(filename).stem
    tokens = tokenize(stem)
    
    result = []
    for t in tokens:
        if t in STOPWORDS:
            continue
        if re.match(r'[\u4e00-\u9fff]+', t):
            if len(t) >= 2:
                result.append(t)
        else:
            if len(t) >= MIN_WORD_LEN:
                result.append(t)
    
    return result


def compute_doc_frequency_from_filenames() -> Tuple[Dict[str, int], int]:
    """基于文件名计算工作区中关键词的文档频率
    
    只使用 Notes 目录下的文件名，不打开文件读取标题。
    
    文档频率：关键词在多少个不同的文件中出现过
    
    Returns:
        (关键词到出现文档数的映射, 总文档数)
    """
    md_files = get_notes_folder_md_files()
    total_docs = len(md_files)
    
    if total_docs == 0:
        return {}, 0
    
    doc_freq = defaultdict(int)
    
    for md_file in md_files:
        try:
            keywords = extract_keywords_from_filename(md_file.name)
            unique_keywords = set(keywords)
            for kw in unique_keywords:
                doc_freq[kw] += 1
        except Exception:
            continue
    
    return dict(doc_freq), total_docs


def extract_tags_by_doc_frequency(
    doc_freq: Dict[str, int],
    total_docs: int,
    current_file_keywords: List[str] = None
) -> List[str]:
    """基于文档频率提取标签
    
    规则：
    1. 排除出现次数不大于 2 的关键词（即出现次数 >= 3）
    2. 按出现次数从高到低排序
    3. 提取最多 5 个标签，最少可以是 0 个
    4. 如果当前有关键词，优先选择当前文件包含的关键词
    
    Args:
        doc_freq: 关键词到出现文档数的映射
        total_docs: 总文档数
        current_file_keywords: 当前文件的关键词列表（可选）
    
    Returns:
        标签列表（0-5 个）
    """
    if not doc_freq or total_docs == 0:
        return []
    
    min_count = MIN_DOC_FREQ_COUNT
    
    candidates = []
    for kw, count in doc_freq.items():
        if count >= min_count:
            in_current = current_file_keywords and kw in current_file_keywords
            candidates.append((kw, count, in_current))
    
    candidates.sort(key=lambda x: (x[2], x[1]), reverse=True)
    
    keywords = [kw for kw, count, in_current in candidates]
    
    return keywords[:MAX_TAGS]


def process_and_tag_file_by_doc_freq(file_path: str) -> List[str]:
    """基于文档频率处理单个文件并打标签
    
    算法规则：
    1. 只使用 Notes 目录下的文件名，不打开文件读取标题
    2. 统计每个关键词的文档频率（出现的文件数）
    3. 备选标签必须在其他 md 文件的文件名中出现过 3 次及以上
    4. 如果不符合第 3 点，就不要加为标签
    5. 标签数量：最多 5 个，最少可以是 0 个、1 个、2 个等
    6. 优先选择当前文件包含的关键词
    7. 排除常用词汇和非专有名词（步骤、功能、方法等）
    
    Args:
        file_path: Markdown 文件路径
    
    Returns:
        标签列表（0-5 个）
    """
    p = Path(file_path)
    if not p.exists() or not p.suffix.lower() == '.md':
        return []
    
    doc_freq, total_docs = compute_doc_frequency_from_filenames()
    
    if total_docs == 0:
        return []
    
    current_file_keywords = extract_keywords_from_filename(p.name)
    
    tags = extract_tags_by_doc_frequency(doc_freq, total_docs, current_file_keywords)
    
    if tags:
        append_tags_to_markdown(str(p), tags)
    
    return tags


def process_and_tag_file(file_path: str, idf: Dict[str, float] = None) -> List[str]:
    """处理单个文件并打标签（使用新的文档频率算法）
    
    这是 process_and_tag_file_by_doc_freq 的别名，
    保持原有接口兼容。
    """
    return process_and_tag_file_by_doc_freq(file_path)


def tag_markdown_files(
    file_paths: List[str],
    all_texts: List[str] = None,
    titles: List[str] = None
) -> Dict[str, List[str]]:
    """对一批 Markdown 文件进行标签提取和追加"""
    if not file_paths:
        return {}

    if all_texts and len(all_texts) == len(file_paths):
        texts = all_texts
    else:
        texts = []
        for fp in file_paths:
            try:
                texts.append(Path(fp).read_text(encoding='utf-8'))
            except Exception:
                texts.append('')

    if titles is None:
        titles = []
        for fp in file_paths:
            try:
                from utils.helpers import extract_title_from_markdown
                content = Path(fp).read_text(encoding='utf-8') if fp not in texts else texts[file_paths.index(fp)]
                titles.append(extract_title_from_markdown(content) or Path(fp).stem)
            except Exception:
                titles.append(Path(fp).stem)

    all_tokens = [tokenize(t) for t in texts]
    idf = compute_idf(all_tokens)

    results = {}
    for i, fp in enumerate(file_paths):
        try:
            tf = compute_tf(all_tokens[i])
            tfidf = compute_tfidf(tf, idf)
            sorted_terms = sorted(tfidf.items(), key=lambda x: x[1], reverse=True)
            tags = [term for term, score in sorted_terms if score >= MIN_TF_IDF_SCORE][:MAX_TAGS]

            title_extra = extract_tags_from_text(titles[i], idf)
            all_tags = tags + title_extra
            seen = set()
            unique_tags = []
            for tag in all_tags:
                if tag not in seen and len(unique_tags) < MAX_TAGS:
                    seen.add(tag)
                    unique_tags.append(tag)

            if unique_tags:
                append_tags_to_markdown(str(fp), unique_tags)
                results[str(fp)] = unique_tags
        except Exception:
            pass

    return results


def _escape_yaml_string(value: str) -> str:
    """
    转义YAML字符串中的特殊字符。
    处理：引号、反斜杠、换行符、冒号后跟空格等。
    """
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
    """
    格式化YAML值，根据类型选择合适的表示方式。
    """
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
    word_count: int = None,
    language: str = "",
    extra_fields: Dict[str, Any] = None
) -> str:
    """
    生成标准的 YAML front matter。
    
    参数：
        title: 文档标题
        tags: 标签列表
        date: 创建/处理日期（默认当前日期）
        source: 来源（URL或文件路径）
        word_count: 字数统计
        language: 语言检测结果（chinese/english）
        extra_fields: 额外的自定义字段
    
    返回：
        完整的 YAML front matter 字符串（包含 --- 分隔符）
    
    格式说明：
        ---
        title: "文档标题"
        tags: [tag1, tag2, tag3]
        date: "2026-04-19"
        source: "https://example.com"
        word_count: 1234
        language: "chinese"
        ---
    
    兼容性：
        - 与 Obsidian、Jekyll、Hugo、Hexo 等主流静态站点生成器兼容
        - 与 VS Code、Typora 等 Markdown 编辑器兼容
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
    
    if word_count is not None:
        fields['word_count'] = word_count
    
    if language:
        fields['language'] = language
    
    if extra_fields:
        fields.update(extra_fields)
    
    lines = ['---']
    
    ordered_keys = ['title', 'tags', 'date', 'source', 'word_count', 'language']
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
    """
    解析 Markdown 文件中的 YAML front matter。
    
    参数：
        content: Markdown 文件完整内容
    
    返回：
        (frontmatter_dict, remaining_content)
        - frontmatter_dict: 解析出的 YAML 字段字典
        - remaining_content: 去除 front matter 后的正文内容
    
    示例：
        content = '''---
        title: "测试"
        tags: [tag1, tag2]
        ---
        
        正文内容
        '''
        frontmatter, body = parse_yaml_frontmatter(content)
        # frontmatter = {'title': '测试', 'tags': ['tag1', 'tag2']}
        # body = '正文内容'
    
    注意：
        - 优先使用 PyYAML 解析（如果已安装）
        - 如果 PyYAML 不可用，使用内置的简单解析器作为 fallback
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
    language: str = "",
    extra_fields: Dict[str, Any] = None
) -> str:
    """
    为 Markdown 内容添加 YAML front matter。
    
    如果内容已存在 front matter，则更新它；否则添加新的。
    
    参数：
        content: 原始 Markdown 内容
        title: 文档标题（如未提供，尝试从内容中提取）
        tags: 标签列表
        source: 来源（URL或文件路径）
        language: 语言
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
        tags = extract_tags_from_text(body)
    
    word_count = len(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+', body))
    
    if not language:
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', body))
        language = 'chinese' if chinese_chars > 10 else 'english'
    
    new_frontmatter = generate_yaml_frontmatter(
        title=title,
        tags=tags,
        source=source,
        word_count=word_count,
        language=language,
        extra_fields=extra_fields
    )
    
    return new_frontmatter + body


def add_yaml_frontmatter_to_file(
    file_path: str,
    title: str = "",
    tags: List[str] = None,
    source: str = "",
    language: str = "",
    extra_fields: Dict[str, Any] = None
) -> bool:
    """
    为 Markdown 文件添加 YAML front matter。
    
    参数：
        file_path: Markdown 文件路径
        title: 文档标题
        tags: 标签列表
        source: 来源
        language: 语言
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
            language=language,
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
    """
    处理单个文件，提取标签并添加 YAML front matter。
    
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
        'word_count': 0,
        'language': ''
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
        
        tags = extract_tags_from_text(body)
        
        word_count = len(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+', body))
        
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', body))
        language = 'chinese' if chinese_chars > 10 else 'english'
        
        new_frontmatter = generate_yaml_frontmatter(
            title=title,
            tags=tags,
            source=source,
            word_count=word_count,
            language=language
        )
        
        new_content = new_frontmatter + body
        p.write_text(new_content, encoding='utf-8')
        
        result['success'] = True
        result['tags'] = tags
        result['title'] = title
        result['word_count'] = word_count
        result['language'] = language
        
        return result
    except Exception as e:
        return result
