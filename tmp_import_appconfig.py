import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'python')
print('step 1', flush=True)
from config.app_config import AppConfig
print('step 2', flush=True)
print('fields:', [f.name for f in AppConfig.__dataclass_fields__.keys()][:5], flush=True)
