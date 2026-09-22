"""Plaintext credential storage in NoteAI's application data directory.

The module name is retained for compatibility with existing imports. NoteAI no
longer reads from or writes to an operating-system keychain, and credentials
are stored as plaintext files (0600) instead of encrypted blobs.

Rationale for dropping Fernet encryption: the previous scheme derived the key
from hostname + user + an install secret, so any hostname change silently
bricked every stored credential with no recovery path. Plaintext in a
user-scoped 0700 directory is an explicit trade-off the product has accepted.
"""

import base64
import hashlib
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_log = logging.getLogger("NoteAI")

# Legacy OS-keychain backend identifiers (pre-2026-08 file-based migration).
_KEYCHAIN_SERVICE = "NoteAI"
_KEYCHAIN_ACCOUNT = "api_key"


def _read_legacy_macos_keychain() -> str:
    """Read a credential previously stored by the pre-2026-08 OS keychain backend.

    Used only as a one-time compatibility migration for users who upgraded after
    NoteAI switched to file-based storage. Returns "" when the entry
    does not exist or the command is unavailable.
    """
    if sys.platform != "darwin":
        return ""
    try:
        proc = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                _KEYCHAIN_SERVICE,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        _log.debug("keychain migration lookup unavailable: %s", exc)
        return ""
    if proc.returncode != 0:
        return ""
    value = (proc.stdout or "").strip()
    return value if value and not value.lower().startswith(("error", "security")) else ""


def _delete_legacy_macos_keychain() -> None:
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(
            ["security", "delete-generic-password", "-s", _KEYCHAIN_SERVICE],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        _log.debug("keychain migration cleanup unavailable: %s", exc)


def _app_data_dir() -> Path:
    # Import from constants (a leaf module) instead of settings to avoid a
    # circular import: settings -> app_config -> keyring_store -> settings.
    from config.constants import SYSTEM_APP_DATA_DIR

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


def _atomic_write(path: Path, value: str, prefix: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=prefix)
        try:
            os.write(fd, value.encode("utf-8"))
        finally:
            os.close(fd)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        _log.warning("Failed to write credential %s: %s", path.name, exc)
        return False


def _read_path(path: Path) -> str:
    """Read a plaintext credential file.

    Unreadable legacy content (e.g. Fernet blobs left by the pre-plaintext
    backend) is treated as missing; the next save overwrites the file.
    """
    if not path.exists():
        return ""
    try:
        os.chmod(path, 0o600)
        return path.read_bytes().decode("utf-8").strip()
    except Exception as exc:
        _log.warning("Failed to read credential %s (treated as missing): %s", path.name, exc)
        return ""


def _delete_path(path: Path) -> bool:
    try:
        if path.exists():
            path.unlink()
        return True
    except Exception as exc:
        _log.warning("Failed to delete credential %s: %s", path.name, exc)
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
    value = _load_with_migration(_fallback_path(), _legacy_fallback_path(), ".api_key_")
    if value:
        return value

    # One-time compatibility migration from the pre-2026-08 OS keychain backend.
    legacy_key = _read_legacy_macos_keychain()
    if not legacy_key:
        return ""
    if _atomic_write(_fallback_path(), legacy_key, ".api_key_"):
        _delete_legacy_macos_keychain()
        _log.info("已从 macOS Keychain 迁移 API key 到本地凭据文件")
        return legacy_key
    return ""


def _credential_filename(service: str, account: str) -> str:
    safe_service = base64.urlsafe_b64encode(hashlib.sha256(service.encode()).digest()).decode()[:16]
    safe_account = base64.urlsafe_b64encode(hashlib.sha256(account.encode()).digest()).decode()[:16]
    return f"cred_{safe_service}_{safe_account}.dat"


def _credential_fallback_path(service: str, account: str) -> Path:
    return _credentials_dir() / _credential_filename(service, account)


def _legacy_credential_fallback_path(service: str, account: str) -> Path:
    return _app_data_dir() / _credential_filename(service, account)


def store_credential(service: str, account: str, value: str) -> bool:
    """Store an arbitrary credential in the application directory."""
    if not value:
        return False
    current = _credential_fallback_path(service, account)
    written = _atomic_write(current, value, ".cred_")
    if written:
        _delete_path(_legacy_credential_fallback_path(service, account))
    return written


def load_credential(service: str, account: str) -> str:
    """Load an arbitrary credential from the application directory."""
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
    return "disabled: using plaintext application directory"
