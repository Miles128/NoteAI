import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'python')
print('before import', flush=True)
from sidecar.rag.retriever import _scan_files
print('after import', flush=True)
