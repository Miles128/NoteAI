"""Tests for keyring-backed API key storage."""


class TestKeyringStore:
    def test_module_imports(self):
        from utils.keyring_store import is_keyring_available, keyring_status, load_api_key

        assert isinstance(is_keyring_available(), bool)
        assert isinstance(load_api_key(), str)
        assert isinstance(keyring_status(), str)
