import sys
import os
import traceback
import faulthandler
import signal
from datetime import datetime

sys.path.insert(0, '.')
sys.path.insert(0, 'python')

os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')
os.environ.setdefault('OMP_NUM_THREADS', '4')

log_path = '/Users/sihai/Documents/My Projects/NoteAI/tmp_rebuild_rag.log'


def log(msg):
    line = f"[{datetime.now().isoformat()}] {msg}"
    print(line, flush=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


faulthandler.enable()
signal.signal(signal.SIGTERM, lambda s, f: log(f"SIGTERM received at {f}"))

log('Starting RAG rebuild...')
log(f'Python executable: {sys.executable}')
log(f'Python version: {sys.version}')

try:
    log('Importing config...')
    from config import config
    log(f'Config workspace: {config.workspace_path}')

    log('Importing rag_config...')
    from sidecar.rag import rag_config
    log('Imported rag_config')

    log('Importing retriever...')
    from sidecar.rag.retriever import rebuild_index
    log('Imported retriever')

    workspace = '/Users/sihai/Documents/My_Notes'
    log(f'Workspace: {workspace}')

    log('Calling rebuild_index...')
    result = rebuild_index(workspace=workspace, force_full=True)
    log(f'Result: {result}')
except Exception as e:
    log(f'ERROR: {type(e).__name__}: {e}')
    traceback.print_exc()
except SystemExit as e:
    log(f'SystemExit: code={e.code}')
    traceback.print_exc()
except BaseException as e:
    log(f'BaseException: {type(e).__name__}: {e}')
    traceback.print_exc()
finally:
    log('Script finished')
