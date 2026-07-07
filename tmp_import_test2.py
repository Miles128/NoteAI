import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'python')
print('step 1', flush=True)
from config import config
print('step 2', flush=True)
from sidecar.rag import retriever
print('step 3', flush=True)
