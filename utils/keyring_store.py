"""Secure API key storage via OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)."""

import base64
import hashlib
import logging
import os
import secrets
import tempfile

_log = logging.getLogger("NoteAI")

_SERVICE_NAME = "NoteAI"
_ACCOUNT_API_KEY = "api_key"

_HAS_KEYRING = False
_keyring_exc = None
try:
    import keyring

    _HAS_KEYRING = True
except ImportError:
    _keyring_exc = "keyring library not installed"


def _fallback_path():
    from config.settings import SYSTEM_APP_DATA_DIR

    SYSTEM_APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return SYSTEM_APP_DATA_DIR / "api_key.dat"


_PBKDF2_ITERATIONS = 100_000


def _derive_fernet_key(salt: bytes) -> bytes:
    """Derive a Fernet key from machine info and a per-installation salt.

    The fallback file stores the salt alongside the ciphertext. This is still
    obfuscation, not true encryption: anyone with the file and the machine
    info can decrypt it. It is only used when the OS keychain is unavailable.
    """
    machine_id = os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "localhost")
    user = os.environ.get("USER", os.environ.get("USERNAME", "user"))
    password = f"NoteAI:{machine_id}:{user}".encode()
    key = hashlib.pbkdf2_hmac("sha256", password, salt, _PBKDF2_ITERATIONS, dklen=32)
    return base64.urlsafe_b64encode(key)


def _encrypt(value: str) -> bytes:
    from cryptography.fernet import Fernet

    salt = secrets.token_bytes(16)
    f = Fernet(_derive_fernet_key(salt))
    ciphertext = f.encrypt(value.encode("utf-8"))
    return base64.b64encode(salt + ciphertext)


def _decrypt(data: bytes) -> str:
    from cryptography.fernet import Fernet

    raw = base64.b64decode(data)
    if len(raw) < 16:
        raise ValueError("Invalid fallback data")
    salt, ciphertext = raw[:16], raw[16:]
    f = Fernet(_derive_fernet_key(salt))
    return f.decrypt(ciphertext).decode("utf-8")


def _fallback_read() -> str:
    path = _fallback_path()
    if not path.exists():
        return ""
    try:
        data = path.read_bytes()
        os.chmod(path, 0o600)
        try:
            return _decrypt(data)
        except Exception:
            return base64.b64decode(data).decode("utf-8")
    except Exception as e:
        _log.warning("Failed to read API key from fallback: %s", e)
        return ""


def _fallback_write(key: str) -> bool:
    path = _fallback_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".api_key_")
        try:
            os.write(fd, _encrypt(key))
        finally:
            os.close(fd)
        os.chmod(tmp, 0o600)
        os.replace(tmp, str(path))
        return True
    except Exception as e:
        _log.warning("Failed to write API key to fallback: %s", e)
        return False


def _fallback_delete() -> bool:
    try:
        path = _fallback_path()
        if path.exists():
            path.unlink()
        return True
    except Exception as e:
        _log.warning("Failed to delete API key fallback: %s", e)
        return False


def store_api_key(api_key: str) -> bool:
    if not api_key:
        return False

    if _HAS_KEYRING:
        try:
            keyring.set_password(_SERVICE_NAME, _ACCOUNT_API_KEY, api_key)
            return True
        except Exception as e:
            _log.warning("Keyring store failed, using fallback: %s", e)

    return _fallback_write(api_key)


def load_api_key() -> str:
    if _HAS_KEYRING:
        try:
            key = keyring.get_password(_SERVICE_NAME, _ACCOUNT_API_KEY)
            if key:
                return key
        except Exception as e:
            _log.warning("Keyring load failed, using fallback: %s", e)

    return _fallback_read()


def delete_api_key() -> bool:
    ok = True
    if _HAS_KEYRING:
        try:
            keyring.delete_password(_SERVICE_NAME, _ACCOUNT_API_KEY)
        except Exception as e:
            _log.warning("Keyring delete failed: %s", e)
            ok = False
    if not _fallback_delete():
        ok = False
    return ok


def is_keyring_available() -> bool:
    return _HAS_KEYRING


def keyring_status() -> str:
    if _HAS_KEYRING:
        return "available"
    return f"unavailable: {_keyring_exc}"
