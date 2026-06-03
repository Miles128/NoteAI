"""Tests for keyring-backed API key storage."""


class TestKeyringStore:
    def test_module_imports(self):
        from utils.keyring_store import is_keyring_available, load_api_key, keyring_status
        assert isinstance(is_keyring_available(), bool)
        assert isinstance(load_api_key(), str)
        assert isinstance(keyring_status(), str)
