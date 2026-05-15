import sys
import pathlib
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import config

workspace_path = config.workspace_path
if not workspace_path:
    print("Error: 未设置工作区路径 (workspace_path)")
    exit(1)
ws = pathlib.Path(workspace_path)

f1 = ws / 'Notes/Harness和Agent前沿发展'
targets1 = list(f1.glob('*野马*'))
if targets1:
    old = targets1[0]
    t = old.read_text(encoding='utf-8')
    m = re.match(r'^---\s*\n(.*?)\n---', t, re.DOTALL)
    if m:
        body = t[m.end():]
        body = re.sub(r'^#\s+.*', '# Harness Engineering技术解读', body, count=1)
        t = t[:m.end()] + '\n' + body
    else:
        t = re.sub(r'^#\s+.*', '# Harness Engineering技术解读', t, count=1)
    old.write_text(t, encoding='utf-8')
    old.rename(old.parent / 'Harness Engineering技术解读.md')
    print('OK: Harness Engineering技术解读.md')

f2 = ws / 'Notes/Skills系统'
targets2 = list(f2.glob('*概念*'))
if targets2:
    old = targets2[0]
    t = old.read_text(encoding='utf-8')
    m = re.match(r'^---\s*\n(.*?)\n---', t, re.DOTALL)
    if m:
        body = t[m.end():]
        body = re.sub(r'^#\s+.*', '# Agent技能革命概念解读', body, count=1)
        t = t[:m.end()] + '\n' + body
    else:
        t = re.sub(r'^#\s+.*', '# Agent技能革命概念解读', t, count=1)
    old.write_text(t, encoding='utf-8')
    old.rename(old.parent / 'Agent技能革命概念解读.md')
    print('OK: Agent技能革命概念解读.md')
