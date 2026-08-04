"""Encrypted credential storage in NoteAI's application data directory.

The module name is retained for compatibility with existing imports. NoteAI no
longer reads from or writes to an operating-system keychain.
"""

import base64
import hashlib
import logging
import os
import secrets
import tempfile
from pathlib import Path

_log = logging.getLogger("NoteAI")

_PBKDF2_ITERATIONS = 600_000


def _app_data_dir() -> Path:
    from config.settings import SYSTEM_APP_DATA_DIR

    return SYSTEM_APP_DATA_DIR


def _credentials_dir() -> Path:
    path = _app_data_dir() / "credentials"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _fallback_path() -> Path:
    return _credentials_dir() / "api_key.dat"


def _legacy_fallback_path() -> Path:
    return _app_data_dir() / "api_key.dat"


def _install_secret_path() -> Path:
    return _credentials_dir() / ".install_secret"


def _legacy_install_secret_path() -> Path:
    return _app_data_dir() / ".install_secret"


def _read_install_secret(path: Path) -> bytes | None:
    if not path.exists():
        return None
    try:
        return base64.b64decode(path.read_bytes())
    except Exception:
        return None


def _load_or_create_install_secret() -> bytes:
    """Load or create the per-installation secret used for local encryption."""
    path = _install_secret_path()
    existing = _read_install_secret(path)
    if existing is not None:
        return existing

    secret = secrets.token_bytes(32)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".install_secret_")
    try:
        os.write(fd, base64.b64encode(secret))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return secret


def _derive_fernet_key(salt: bytes, install_secret: bytes | None = None) -> bytes:
    """Derive a local encryption key from machine, user, and install data.

    The install secret lives beside the encrypted credentials. This protects
    against accidental plaintext disclosure, but is not equivalent to hardware
    backed or OS-keychain protection.
    """
    machine_id = os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "localhost")
    user = os.environ.get("USER", os.environ.get("USERNAME", "user"))
    secret = install_secret or b""
    password = b"NoteAI:" + machine_id.encode() + b":" + user.encode() + b":" + secret
    key = hashlib.pbkdf2_hmac("sha256", password, salt, _PBKDF2_ITERATIONS, dklen=32)
    return base64.urlsafe_b64encode(key)


def _encrypt(value: str) -> bytes:
    from cryptography.fernet import Fernet

    salt = secrets.token_bytes(16)
    fernet = Fernet(_derive_fernet_key(salt, _load_or_create_install_secret()))
    return base64.b64encode(salt + fernet.encrypt(value.encode("utf-8")))


def _decrypt(data: bytes, install_secret: bytes | None = None) -> str:
    from cryptography.fernet import Fernet

    if install_secret is None:
        install_secret = _load_or_create_install_secret()
    raw = base64.b64decode(data)
    if len(raw) < 16:
        raise ValueError("Invalid credential data")
    salt, ciphertext = raw[:16], raw[16:]
    return Fernet(_derive_fernet_key(salt, install_secret)).decrypt(ciphertext).decode("utf-8")


def _decrypt_compatible(data: bytes) -> str:
    """Read current data and formats used by earlier file-based storage."""
    secrets_to_try = [_load_or_create_install_secret()]
    legacy_secret = _read_install_secret(_legacy_install_secret_path())
    if legacy_secret is not None and legacy_secret not in secrets_to_try:
        secrets_to_try.append(legacy_secret)

    for install_secret in secrets_to_try:
        try:
            return _decrypt(data, install_secret)
        except Exception:
            pass

    # Compatibility with the oldest machine/user-derived format.
    try:
        return _decrypt(data, b"")
    except Exception:
        return base64.b64decode(data).decode("utf-8")


def _atomic_write(path: Path, value: str, prefix: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=prefix)
        try:
            os.write(fd, _encrypt(value))
        finally:
            os.close(fd)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        _log.warning("Failed to write encrypted credential %s: %s", path.name, exc)
        return False


def _read_path(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        os.chmod(path, 0o600)
        return _decrypt_compatible(path.read_bytes())
    except Exception as exc:
        _log.warning("Failed to read encrypted credential %s: %s", path.name, exc)
        return ""


def _delete_path(path: Path) -> bool:
    try:
        if path.exists():
            path.unlink()
        return True
    except Exception as exc:
        _log.warning("Failed to delete encrypted credential %s: %s", path.name, exc)
        return False


def _load_with_migration(current: Path, legacy: Path, prefix: str) -> str:
    value = _read_path(current)
    if value or not legacy.exists():
        return value

    value = _read_path(legacy)
    if value and _atomic_write(current, value, prefix):
        _delete_path(legacy)
    return value


def store_api_key(api_key: str) -> bool:
    if not api_key:
        return False
    written = _atomic_write(_fallback_path(), api_key, ".api_key_")
    if written:
        _delete_path(_legacy_fallback_path())
    return written


def load_api_key() -> str:
    return _load_with_migration(_fallback_path(), _legacy_fallback_path(), ".api_key_")


def delete_api_key() -> bool:
    current_deleted = _delete_path(_fallback_path())
    legacy_deleted = _delete_path(_legacy_fallback_path())
    return current_deleted and legacy_deleted


def _credential_filename(service: str, account: str) -> str:
    safe_service = base64.urlsafe_b64encode(hashlib.sha256(service.encode()).digest()).decode()[:16]
    safe_account = base64.urlsafe_b64encode(hashlib.sha256(account.encode()).digest()).decode()[:16]
    return f"cred_{safe_service}_{safe_account}.dat"


def _credential_fallback_path(service: str, account: str) -> Path:
    return _credentials_dir() / _credential_filename(service, account)


def _legacy_credential_fallback_path(service: str, account: str) -> Path:
    return _app_data_dir() / _credential_filename(service, account)


def store_credential(service: str, account: str, value: str) -> bool:
    """Store an arbitrary credential in the encrypted application directory."""
    if not value:
        return False
    current = _credential_fallback_path(service, account)
    written = _atomic_write(current, value, ".cred_")
    if written:
        _delete_path(_legacy_credential_fallback_path(service, account))
    return written


def load_credential(service: str, account: str) -> str:
    """Load an arbitrary credential from the encrypted application directory."""
    return _load_with_migration(
        _credential_fallback_path(service, account),
        _legacy_credential_fallback_path(service, account),
        ".cred_",
    )


def delete_credential(service: str, account: str) -> bool:
    """Delete an arbitrary credential from current and legacy file locations."""
    current_deleted = _delete_path(_credential_fallback_path(service, account))
    legacy_deleted = _delete_path(_legacy_credential_fallback_path(service, account))
    return current_deleted and legacy_deleted


def is_keyring_available() -> bool:
    """Compatibility API: OS keyrings are intentionally disabled."""
    return False


def keyring_status() -> str:
    """Compatibility API describing the configured storage backend."""
    return "disabled: using encrypted application directory"
