#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试主题整合功能的优化效果
"""

import time
from pathlib import Path
from modules.note_integration import NoteIntegration


def test_optimization():
    """测试优化效果"""
    # 准备测试数据
    test_folder = Path(__file__).parent / "tests" / "test_data"
    if not test_folder.exists():
        # 创建测试数据目录
        test_folder.mkdir(parents=True, exist_ok=True)
        
        # 创建一些测试Markdown文件
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
    
    # 初始化整合器
    def progress_callback(current, total, message):
        print(f"进度: {current}/{total} - {message}")
    
    integrator = NoteIntegration(progress_callback=progress_callback)
    
    # 加载文档
    print("加载文档...")
    documents = integrator.load_documents_from_folder(str(test_folder))
    
    # 运行整合
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
