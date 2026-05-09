import shutil
from pathlib import Path

workspace = Path('/Users/sihai/Documents/My Notes')
src = workspace / 'Organized'
dst = workspace / 'Abstract'

if src.exists() and not dst.exists():
    src.rename(dst)
    print(f'已重命名: Organized -> Abstract')
elif dst.exists():
    print('Abstract 文件夹已存在')
elif not src.exists():
    print('Organized 文件夹不存在')
