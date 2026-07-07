import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'python')
from pathlib import Path
from sidecar.rag.retriever import _scan_files
print('Scanning files...', flush=True)
files = _scan_files(Path('/Users/sihai/Documents/My_Notes'))
print(f'Found {len(files)} files', flush=True)
