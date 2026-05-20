import base64
import os
import sys


def _obfuscate(value: str) -> str:
    return base64.b64encode(value.encode('utf-8')).decode('ascii')


def _deobfuscate(value: str) -> str:
    try:
        return base64.b64decode(value.encode('ascii')).decode('utf-8')
    except Exception:
        return value


def _restrict_file_permissions(filepath: str):
    try:
        os.chmod(filepath, 0o600)
    except Exception as e:
        sys.stderr.write(f"[security] restrict permissions failed: {e}\n")
        sys.stderr.flush()