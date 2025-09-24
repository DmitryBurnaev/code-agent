import base64

import pytest
from pydantic import SecretStr

from src.modules.encrypt.encryption import VendorKeyEncryption


class TestVendorKeyEncryption:

    def test_encrypt_decrypt_roundtrip(self) -> None:
        secret_key = SecretStr("test-secret-key-32-chars-long")
        encryption = VendorKeyEncryption(secret_key)

        original_key = "sk-test123456789"
        encrypted = encryption.encrypt(original_key)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == original_key
        assert encrypted != original_key

    def test_encrypt_empty_string(self) -> None:
        secret_key = SecretStr("test-secret-key-32-chars-long")
        encryption = VendorKeyEncryption(secret_key)

        with pytest.raises(ValueError, match="Plaintext cannot be empty"):
            encryption.encrypt("")

    def test_decrypt_empty_string(self) -> None:
        secret_key = SecretStr("test-secret-key-32-chars-long")
        encryption = VendorKeyEncryption(secret_key)

        with pytest.raises(ValueError, match="Encrypted data cannot be empty"):
            encryption.decrypt("")

    def test_decrypt_invalid_data(self) -> None:
        secret_key = SecretStr("test-secret-key-32-chars-long")
        encryption = VendorKeyEncryption(secret_key)

        with pytest.raises(ValueError):
            encryption.decrypt("invalid-base64-data")

    def test_decrypt_short_data(self) -> None:
        secret_key = SecretStr("test-secret-key-32-chars-long")
        encryption = VendorKeyEncryption(secret_key)

        short_data = base64.b64encode(b"short").decode()

        with pytest.raises(ValueError, match="Failed to decrypt API key"):
            encryption.decrypt(short_data)

    def test_is_encrypted_valid_data(self) -> None:
        secret_key = SecretStr("test-secret-key-32-chars-long")
        encryption = VendorKeyEncryption(secret_key)

        original_key = "sk-test123456789"
        encrypted = encryption.encrypt(original_key)

        assert encryption.is_encrypted(encrypted) is True

    def test_is_encrypted_plaintext(self) -> None:
        secret_key = SecretStr("test-secret-key-32-chars-long")
        encryption = VendorKeyEncryption(secret_key)

        assert encryption.is_encrypted("plaintext-key") is False
        assert encryption.is_encrypted("") is False

    def test_is_encrypted_invalid_base64(self) -> None:
        secret_key = SecretStr("test-secret-key-32-chars-long")
        encryption = VendorKeyEncryption(secret_key)

        assert encryption.is_encrypted("invalid-base64!@#") is False

    def test_different_keys_produce_different_encryption(self) -> None:
        secret_key = SecretStr("test-secret-key-32-chars-long")
        encryption = VendorKeyEncryption(secret_key)

        original_key = "sk-test123456789"
        encrypted1 = encryption.encrypt(original_key)
        encrypted2 = encryption.encrypt(original_key)

        assert encrypted1 != encrypted2
        assert encryption.decrypt(encrypted1) == original_key
        assert encryption.decrypt(encrypted2) == original_key
