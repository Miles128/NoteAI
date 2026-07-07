import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'python')
print('step 1', flush=True)
from config.app_config import AppConfig
print('step 2', flush=True)
cfg = AppConfig.load_from_file()
print('step 3', flush=True)
print('workspace:', cfg.workspace_path, flush=True)
print('rag_enabled:', cfg.rag_enabled, flush=True)
