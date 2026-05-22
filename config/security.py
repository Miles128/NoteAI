import os
import sys

from cryptography.fernet import Fernet
import base64
import hashlib


def _derive_key() -> bytes:
    machine_id = os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'localhost')
    user = os.environ.get('USER', os.environ.get('USERNAME', 'user'))
    seed = f"NoteAI:{machine_id}:{user}".encode()
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


def _get_fernet() -> Fernet:
    return Fernet(_derive_key())


def _obfuscate(value: str) -> str:
    f = _get_fernet()
    return f.encrypt(value.encode('utf-8')).decode('ascii')


def _deobfuscate(value: str) -> str:
    try:
        f = _get_fernet()
        return f.decrypt(value.encode('ascii')).decode('utf-8')
    except Exception:
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
