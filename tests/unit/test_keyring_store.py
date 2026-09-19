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

    def test_plaintext_roundtrip(self, monkeypatch, tmp_path):
        from config import constants
        from utils.keyring_store import _fallback_path, load_api_key, store_api_key

        monkeypatch.setattr(constants, "SYSTEM_APP_DATA_DIR", tmp_path)

        assert store_api_key("sk-plain-12345") is True
        assert _fallback_path().read_bytes().decode("utf-8").strip() == "sk-plain-12345"
        assert load_api_key() == "sk-plain-12345"

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
        from utils.keyring_store import load_api_key

        monkeypatch.setattr(constants, "SYSTEM_APP_DATA_DIR", tmp_path)

        legacy_path = tmp_path / "api_key.dat"
        legacy_path.write_text("sk-legacy-plaintext", encoding="utf-8")

        assert load_api_key() == "sk-legacy-plaintext"
        assert not legacy_path.exists()
        assert (tmp_path / "credentials" / "api_key.dat").exists()

    def test_unreadable_legacy_blob_treated_as_missing(self, monkeypatch, tmp_path):
        """Fernet blobs from the pre-plaintext backend decode as garbage → treated as missing."""
        from config import constants
        from utils.keyring_store import _fallback_path, load_api_key, store_api_key

        monkeypatch.setattr(constants, "SYSTEM_APP_DATA_DIR", tmp_path)

        credentials_dir = tmp_path / "credentials"
        credentials_dir.mkdir(parents=True)
        (credentials_dir / "api_key.dat").write_bytes(b"\x00\xe6garbage-not-utf8")

        assert load_api_key() == ""
        assert store_api_key("sk-new-key") is True
        assert load_api_key() == "sk-new-key"
        assert _fallback_path().read_bytes().decode("utf-8").strip() == "sk-new-key"
