"""Tests for keyring-backed API key storage."""


class TestKeyringStore:
    def test_module_imports(self):
        from utils.keyring_store import is_keyring_available, keyring_status, load_api_key

        assert isinstance(is_keyring_available(), bool)
        assert isinstance(load_api_key(), str)
        assert isinstance(keyring_status(), str)

    def test_fallback_encrypt_decrypt_roundtrip(self):
        from utils.keyring_store import _decrypt, _encrypt

        key = "sk-test-12345"
        encrypted = _encrypt(key)
        assert encrypted != key.encode()
        decrypted = _decrypt(encrypted)
        assert decrypted == key
