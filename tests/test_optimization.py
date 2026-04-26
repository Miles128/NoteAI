#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.note_integration import NoteIntegration


def test_optimization():
    test_folder = Path(__file__).parent / "test_data"
    if not test_folder.exists():
        test_folder.mkdir(parents=True, exist_ok=True)

        for i in range(5):
            test_file = test_folder / f"test_{i+1}.md"
            content = f"""# 测试文档 {i+1}

## 主题 A
这是主题 A 的内容，包含一些测试文本。
这是主题 A 的更多内容，用于测试压缩功能。
这是主题 A 的详细内容，确保有足够的字数。

## 主题 B
这是主题 B 的内容，包含一些测试文本。
这是主题 B 的更多内容，用于测试压缩功能。

## 主题 C
这是主题 C 的内容，包含一些测试文本。
这是主题 C 的更多内容，用于测试压缩功能。
"""
            test_file.write_text(content, encoding='utf-8')

    def progress_callback(current, total, message, overall):
        print(f"进度: {current}/{total} - {message}")

    integrator = NoteIntegration(progress_callback=progress_callback)

    print("加载文档...")
    documents = integrator.load_documents_from_folder(str(test_folder))

    print("\n开始整合...")
    start_time = time.time()

    try:
        result = integrator.integrate(
            documents,
            save_path=str(test_folder / "output"),
            user_topics=["测试主题"]
        )

        end_time = time.time()
        execution_time = end_time - start_time

        print("\n整合完成！")
        print(f"执行时间: {execution_time:.2f} 秒")
        print(f"文档数量: {result['document_count']}")
        print(f"主题数量: {result['topic_count']}")
        print(f"生成文件: {len(result['file_paths'])}")
        print(f"主题列表: {result['topics']}")

    except Exception as e:
        print(f"整合失败: {e}")
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"执行时间: {execution_time:.2f} 秒")


if __name__ == "__main__":
    test_optimization()
