"""Tests for application-directory credential storage."""

import os


class TestKeyringStore:
    def test_module_uses_application_directory(self, monkeypatch, tmp_path):
        from config import constants
        from utils.keyring_store import (
            _fallback_path,
            is_keyring_available,
            keyring_status,
            load_api_key,
            store_api_key,
        )

        monkeypatch.setattr(constants, "SYSTEM_APP_DATA_DIR", tmp_path)

        assert is_keyring_available() is False
        assert "application directory" in keyring_status()
        assert store_api_key("sk-test-application-dir") is True
        assert load_api_key() == "sk-test-application-dir"
        assert _fallback_path() == tmp_path / "credentials" / "api_key.dat"
        if os.name != "nt":
            assert _fallback_path().stat().st_mode & 0o777 == 0o600
            assert _fallback_path().parent.stat().st_mode & 0o777 == 0o700

    def test_fallback_encrypt_decrypt_roundtrip(self, monkeypatch, tmp_path):
        from config import constants
        from utils.keyring_store import _decrypt, _encrypt

        monkeypatch.setattr(constants, "SYSTEM_APP_DATA_DIR", tmp_path)

        key = "sk-test-12345"
        encrypted = _encrypt(key)
        assert encrypted != key.encode()
        decrypted = _decrypt(encrypted)
        assert decrypted == key

    def test_generic_credential_roundtrip(self, monkeypatch, tmp_path):
        from config import constants
        from utils.keyring_store import delete_credential, load_credential, store_credential

        monkeypatch.setattr(constants, "SYSTEM_APP_DATA_DIR", tmp_path)

        assert store_credential("NoteAI/cloud_sync", "webdav/password", "secret")
        assert load_credential("NoteAI/cloud_sync", "webdav/password") == "secret"
        assert delete_credential("NoteAI/cloud_sync", "webdav/password")
        assert load_credential("NoteAI/cloud_sync", "webdav/password") == ""

    def test_legacy_file_is_migrated(self, monkeypatch, tmp_path):
        from config import constants
        from utils.keyring_store import _encrypt, load_api_key

        monkeypatch.setattr(constants, "SYSTEM_APP_DATA_DIR", tmp_path)

        legacy_data = _encrypt("sk-legacy-encrypted")
        credentials_dir = tmp_path / "credentials"
        (credentials_dir / ".install_secret").replace(tmp_path / ".install_secret")
        (tmp_path / "api_key.dat").write_bytes(legacy_data)

        assert load_api_key() == "sk-legacy-encrypted"
        assert not (tmp_path / "api_key.dat").exists()
        assert (credentials_dir / "api_key.dat").exists()
