#!/usr/bin/env python3
"""将挤在一行的 MD 文件拆解为有标题层级的标准格式"""
import re, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
NOTES_DIR = PROJECT_ROOT / "src-tauri" / "Notes"

def reorganize(content):
    lines = content.split('\n')
    
    # 找到 frontmatter 结束位置
    body_start = 0
    in_frontmatter = False
    for i, line in enumerate(lines):
        if line.strip() == '---':
            if not in_frontmatter:
                in_frontmatter = True
            else:
                body_start = i + 1
                break
    
    frontmatter = '\n'.join(lines[:body_start])
    body = '\n'.join(lines[body_start:])
    
    # 提取正文（跳过开头的 # 标题行，因为内容与 frontmatter title 重复）
    body_lines = body.strip().split('\n')
    
    # 找到第一个非空、非标题行（真正的正文开始）
    # 通常第7行是 # 开头的重复标题，正文从那之后开始
    clean_lines = []
    found_first_h1 = False
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('# ') and not found_first_h1:
            found_first_h1 = True
            continue  # 跳过重复的一级标题
        clean_lines.append(stripped)
    
    if not clean_lines:
        return content
    
    # 将所有行合并为一段文本
    text = ' '.join(clean_lines)
    
    # 识别关键模式来插入标题
    # 模式1: "关键词：描述" 格式（中文冒号后跟描述，通常是主题句）
    # 模式2: 加粗文本 **...** 后跟描述（通常是主题句）
    
    # 按自然语言边界分段
    # 先按句号+空格分段，然后识别主题句
    
    # 简单策略：按 "**...**" 和 "关键词：" 模式识别主题
    # 将文本按这些模式拆分
    
    segments = []
    # 匹配模式: 独立的加粗文本 或 "XXX：" 格式的主题句
    pattern = r'(?=(?:\*\*[^*]+\*\*(?=[，。：\s]|$))|(?:[^\s，。]{2,10}[：]))'
    
    # 更简单的方法：按已知的关键词分段
    # 识别 "OpenClaw：" "Claude Code：" "Hermes：" 等框架名称开头的段落
    # 以及 "### " "## " 等已有标题
    
    # 最终策略：将文本按句号分段，每3-5句为一段落
    sentences = re.split(r'(?<=[。！？])\s*', text)
    
    paragraphs = []
    current_para = []
    sentence_count = 0
    
    for sent in sentences:
        if not sent.strip():
            continue
        current_para.append(sent.strip())
        sentence_count += 1
        
        # 检查是否是主题句（以框架名开头，或包含冒号主题）
        is_topic = bool(re.match(r'^(OpenClaw|Claude Code|Hermes|三个框架|这|但|而|然而)', sent.strip()))
        
        if sentence_count >= 3 and (is_topic or sentence_count >= 5):
            paragraphs.append('。'.join(current_para))
            current_para = []
            sentence_count = 0
    
    if current_para:
        paragraphs.append('。'.join(current_para))
    
    # 重建正文
    title_match = re.search(r'title:\s*"?([^"\n]+)"?', frontmatter)
    title = title_match.group(1) if title_match else "未命名文章"
    # 清理 title 中的多余信息
    title = re.sub(r'\s*目标：.*$', '', title)
    title = re.sub(r'\*\*', '', title)
    title = title.strip()
    
    result_lines = [frontmatter, '', f'# {title}', '']
    for i, para in enumerate(paragraphs):
        result_lines.append(para)
        result_lines.append('')
    
    return '\n'.join(result_lines)

def main():
    # 只处理二级标题<=2的文件
    for f in NOTES_DIR.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        h2_count = len(re.findall(r'^## ', content, re.MULTILINE))
        if h2_count <= 2:
            print(f"处理: {f.name} (h2={h2_count})")
            result = reorganize(content)
            # 先输出预览
            preview = result[:500]
            print(f"预览:\n{preview}\n---")

if __name__ == "__main__":
    main()
