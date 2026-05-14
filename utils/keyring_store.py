"""Secure API key storage via OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)."""

import sys
import logging

_log = logging.getLogger("NoteAI")

_SERVICE_NAME = "NoteAI"
_ACCOUNT_API_KEY = "api_key"

# Platform-specific keyring backend detection
_HAS_KEYRING = False
_keyring_exc = None
try:
    import keyring
    _HAS_KEYRING = True
except ImportError:
    _keyring_exc = "keyring library not installed"


def _fallback_path():
    """Fallback file path when keyring is unavailable."""
    from pathlib import Path
    from config.settings import SYSTEM_APP_DATA_DIR
    SYSTEM_APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return SYSTEM_APP_DATA_DIR / "api_key.dat"


def _fallback_read() -> str:
    """Read from fallback file (base64, 600 perms)."""
    import os
    import base64
    path = _fallback_path()
    if not path.exists():
        return ""
    try:
        data = path.read_bytes()
        os.chmod(path, 0o600)
        return base64.b64decode(data).decode("utf-8")
    except Exception as e:
        _log.warning("Failed to read API key from fallback: %s", e)
        return ""


def _fallback_write(key: str) -> bool:
    """Write to fallback file (base64, 600 perms) via atomic temp+rename."""
    import os
    import base64
    import tempfile
    path = _fallback_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".api_key_")
        try:
            os.write(fd, base64.b64encode(key.encode("utf-8")))
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
    """Store API key in OS keychain. Falls back to encrypted file."""
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
    """Load API key from OS keychain. Falls back to encrypted file."""
    if _HAS_KEYRING:
        try:
            key = keyring.get_password(_SERVICE_NAME, _ACCOUNT_API_KEY)
            if key:
                return key
        except Exception as e:
            _log.warning("Keyring load failed, using fallback: %s", e)

    return _fallback_read()


def delete_api_key() -> bool:
    """Delete API key from OS keychain and fallback."""
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
    """Check if the system keychain is ready."""
    return _HAS_KEYRING


def keyring_status() -> str:
    """Return human-readable keyring availability status."""
    if _HAS_KEYRING:
        return "available"
    return f"unavailable: {_keyring_exc}"
