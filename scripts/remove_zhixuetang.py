import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import config, is_ignored_dir


def remove_zhixuetang(text):
    """
    删除'知学堂'三个字，支持被换行符/空白分隔的情况
    
    支持的模式：
    - '知学堂' → ''
    - '知\n学堂' → ''
    - '知学\n堂' → ''
    - '知\n学\n堂' → ''
    - '知 \n 学 \n 堂' → '' (带空白)
    """
    chars = ['知', '学', '堂']
    result = text
    max_whitespace = 20

    found = True
    while found:
        found = False
        for i in range(len(result)):
            if result[i] != chars[0]:
                continue

            remaining = result[i + 1:]
            idx2 = -1
            for j in range(min(max_whitespace, len(remaining))):
                if remaining[j] == chars[1]:
                    idx2 = j
                    break
            if idx2 < 0:
                continue

            after_idx2 = remaining[idx2 + 1:]
            idx3 = -1
            for j in range(min(max_whitespace, len(after_idx2))):
                if after_idx2[j] == chars[2]:
                    idx3 = j
                    break
            if idx3 < 0:
                continue

            end_pos = i + 1 + idx2 + 1 + idx3 + 1
            result = result[:i] + result[end_pos:]
            found = True
            break

    return result


def main():
    workspace = config.workspace_path
    if not workspace:
        print("未设置工作区")
        return

    workspace = Path(workspace)
    if not workspace.exists():
        print(f"工作区不存在: {workspace}")
        return

    print(f"工作区: {workspace}")
    print("=" * 60)

    modified_count = 0
    file_count = 0

    def scan(path):
        nonlocal modified_count, file_count
        try:
            for entry in sorted(Path(path).iterdir(), key=lambda p: p.name.lower()):
                if entry.name.startswith('.'):
                    continue
                if entry.is_dir():
                    if is_ignored_dir(entry.name):
                        continue
                    scan(str(entry))
                elif entry.suffix.lower() == '.md':
                    file_count += 1
                    try:
                        original = entry.read_text(encoding='utf-8')
                        modified = remove_zhixuetang(original)

                        if modified != original:
                            diff_len = len(original) - len(modified)
                            print(f"[修改] {entry.relative_to(workspace)}  (删除约 {diff_len} 字符)")
                            entry.write_text(modified, encoding='utf-8')
                            modified_count += 1
                    except Exception as e:
                        print(f"[错误] {entry.relative_to(workspace)}: {e}")
        except PermissionError:
            pass

    scan(str(workspace))

    print("=" * 60)
    print(f"总计扫描 {file_count} 个文件")
    print(f"修改 {modified_count} 个文件")


if __name__ == "__main__":
    main()
