#!/usr/bin/env python3
import sys, re, json, time
from pathlib import Path
from openai import OpenAI

PROJECT_ROOT = Path(__file__).parent.parent
NOTES_DIR = PROJECT_ROOT / "src-tauri" / "Notes"
CONFIG_PATH = Path.home() / "Library" / "Application Support" / "NoteAI" / "api_config.json"

PROMPT = """你是一位专业的文档编辑。请将以下文章重新整理为规范的 Markdown 格式。

要求：
1. 文章必须有一个一级标题（#），作为文章的主标题
2. 根据内容逻辑，划分出 3-8 个二级标题（##），每个二级标题下有明确的主题
3. 如果二级标题下的内容较多，进一步使用三级标题（###）细分
4. 正文内容保持原文意思不变，但精简冗余表述
5. 保留原文中的所有关键信息和观点，不遗漏重要内容
6. 保留原文中的代码块、列表、引用等格式
7. 输出只包含整理后的 Markdown 内容，不要添加任何解释说明

原文内容：
{content}"""

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def count_h2(filepath):
    return len(re.findall(r'^## ', filepath.read_text(encoding="utf-8"), re.MULTILINE))

def call_llm(cfg, content):
    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["api_base"])
    resp = client.chat.completions.create(
        model=cfg["model_name"],
        messages=[{"role": "user", "content": PROMPT.format(content=content)}],
        temperature=0.3,
        max_tokens=cfg.get("max_tokens", 32000)
    )
    return resp.choices[0].message.content.strip()

def main():
    cfg = load_config()
    if not cfg.get("api_key"):
        print("错误: 请先配置 API Key"); sys.exit(1)

    target_files = [(f, count_h2(f)) for f in NOTES_DIR.glob("*.md") if count_h2(f) <= 2]
    print(f"二级标题≤2的文件: {len(target_files)} 个")
    for f, h2 in target_files:
        print(f"  [{h2}个h2] {f.name}")

    success = failed = 0
    for f, h2 in target_files:
        print(f"\n处理: {f.name} (当前{h2}个二级标题)")
        content = f.read_text(encoding="utf-8")
        if len(content) < 100:
            print("  内容过短，跳过"); failed += 1; continue
        try:
            result = call_llm(cfg, content)
            if not result or len(result) < 50:
                print("  LLM返回过短，跳过"); failed += 1; continue
            new_h2 = len(re.findall(r'^## ', result, re.MULTILINE))
            f.write_text(result, encoding="utf-8")
            print(f"  完成: {h2} -> {new_h2} 个二级标题")
            success += 1
        except Exception as e:
            print(f"  失败: {e}"); failed += 1
        time.sleep(2)

    print(f"\n完成: 成功 {success}, 失败 {failed}")

if __name__ == "__main__":
    main()
