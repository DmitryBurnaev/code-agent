"""Tests for authentication hashers module."""

import hashlib
import pytest
from unittest.mock import patch, MagicMock

from src.modules.auth.hashers import (
    get_salt,
    get_random_hash,
    PBKDF2PasswordHasher,
)


class TestGetSalt:
    """Tests for salt generation function."""

    def test_get_salt_default_length(self) -> None:
        """Test salt generation with default length."""
        salt = get_salt()

        assert isinstance(salt, str)
        assert len(salt) == 12
        assert salt.isalnum()

    def test_get_salt_custom_length(self) -> None:
        """Test salt generation with custom length."""
        salt = get_salt(length=20)

        assert isinstance(salt, str)
        assert len(salt) == 20
        assert salt.isalnum()

    def test_get_salt_different_salts(self) -> None:
        """Test that different salts are generated."""
        salt1 = get_salt()
        salt2 = get_salt()

        assert salt1 != salt2

    def test_get_salt_allowed_characters(self) -> None:
        """Test that salt contains only allowed characters."""
        salt = get_salt(length=50)

        # Should contain only letters and digits
        assert all(c.isalnum() for c in salt)
        # Should not contain special characters
        assert not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in salt)


class TestGetRandomHash:
    """Tests for random hash generation function."""

    def test_get_random_hash_default_size(self) -> None:
        """Test random hash generation with default size."""
        hash_value = get_random_hash(size=32)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 32
        assert hash_value.isalnum()

    def test_get_random_hash_custom_size(self) -> None:
        """Test random hash generation with custom size."""
        hash_value = get_random_hash(size=64)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64
        assert hash_value.isalnum()

    def test_get_random_hash_different_hashes(self) -> None:
        """Test that different hashes are generated."""
        hash1 = get_random_hash(size=32)
        hash2 = get_random_hash(size=32)

        assert hash1 != hash2

    def test_get_random_hash_hex_format(self) -> None:
        """Test that hash is in hexadecimal format."""
        hash_value = get_random_hash(size=16)

        # Should contain only hexadecimal characters
        assert all(c in "0123456789abcdef" for c in hash_value)


class TestPBKDF2PasswordHasher:
    """Tests for PBKDF2PasswordHasher class."""

    @pytest.fixture
    def hasher(self) -> PBKDF2PasswordHasher:
        """Return PBKDF2PasswordHasher instance."""
        return PBKDF2PasswordHasher()

    def test_hasher_attributes(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test hasher class attributes."""
        assert hasher.algorithm == "pbkdf2_sha256"
        assert hasher.iterations == 180000
        assert hasher.digest == hashlib.sha256

    def test_encode_basic(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test basic password encoding."""
        password = "test-password-123"
        encoded = hasher.encode(password)

        assert isinstance(encoded, str)
        assert encoded.startswith("pbkdf2_sha256$")
        assert encoded.count("$") == 3

    def test_encode_with_custom_salt(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test password encoding with custom salt."""
        password = "test-password-123"
        salt = "custom-salt-123"
        encoded = hasher.encode(password, salt)

        assert isinstance(encoded, str)
        assert encoded.startswith("pbkdf2_sha256$")
        assert salt in encoded

    def test_encode_format(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test that encoded password has correct format."""
        password = "test-password-123"
        encoded = hasher.encode(password)

        parts = encoded.split("$")
        assert len(parts) == 4
        assert parts[0] == "pbkdf2_sha256"
        assert parts[1] == "180000"
        assert len(parts[2]) > 0  # salt
        assert len(parts[3]) > 0  # hash

    def test_encode_different_passwords(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test that different passwords produce different encodings."""
        password1 = "password1"
        password2 = "password2"

        encoded1 = hasher.encode(password1)
        encoded2 = hasher.encode(password2)

        assert encoded1 != encoded2

    def test_encode_same_password_different_salts(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test that same password with different salts produces different encodings."""
        password = "test-password"
        salt1 = "salt1"
        salt2 = "salt2"

        encoded1 = hasher.encode(password, salt1)
        encoded2 = hasher.encode(password, salt2)

        assert encoded1 != encoded2

    def test_verify_correct_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verification of correct password."""
        password = "test-password-123"
        encoded = hasher.encode(password)

        is_valid, message = hasher.verify(password, encoded)

        assert is_valid is True
        assert message == ""

    def test_verify_incorrect_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verification of incorrect password."""
        password = "test-password-123"
        wrong_password = "wrong-password"
        encoded = hasher.encode(password)

        is_valid, message = hasher.verify(wrong_password, encoded)

        assert is_valid is False
        assert message == ""

    def test_verify_with_custom_salt(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verification with custom salt."""
        password = "test-password-123"
        salt = "custom-salt-123"
        encoded = hasher.encode(password, salt)

        is_valid, message = hasher.verify(password, encoded)

        assert is_valid is True
        assert message == ""

    def test_verify_malformed_encoded_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verification with malformed encoded password."""
        password = "test-password-123"
        malformed_encoded = "invalid-format"

        is_valid, message = hasher.verify(password, malformed_encoded)

        assert is_valid is False
        assert "incompatible format" in message

    def test_verify_wrong_algorithm(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verification with wrong algorithm in encoded password."""
        password = "test-password-123"
        wrong_algorithm_encoded = "wrong_algorithm$180000$salt$hash"

        is_valid, message = hasher.verify(password, wrong_algorithm_encoded)

        assert is_valid is False
        assert "Algorithm mismatch" in message

    def test_verify_empty_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verification with empty password."""
        password = ""
        encoded = hasher.encode(password)

        is_valid, message = hasher.verify(password, encoded)

        assert is_valid is True
        assert message == ""

    def test_verify_special_characters_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verification with password containing special characters."""
        password = "test@password#123$%^&*()"
        encoded = hasher.encode(password)

        is_valid, message = hasher.verify(password, encoded)

        assert is_valid is True
        assert message == ""

    def test_verify_unicode_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verification with unicode password."""
        password = "тест-пароль-123"
        encoded = hasher.encode(password)

        is_valid, message = hasher.verify(password, encoded)

        assert is_valid is True
        assert message == ""

    def test_verify_very_long_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verification with very long password."""
        password = "a" * 1000  # Very long password
        encoded = hasher.encode(password)

        is_valid, message = hasher.verify(password, encoded)

        assert is_valid is True
        assert message == ""

    def test_encode_none_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test encoding with None password (should raise assertion)."""
        with pytest.raises(AssertionError):
            hasher.encode(None)  # type: ignore

    def test_encode_empty_salt(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test encoding with empty salt (should raise assertion)."""
        with pytest.raises(AssertionError):
            hasher.encode("password", "")

    def test_encode_salt_with_dollar(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test encoding with salt containing dollar sign (should raise assertion)."""
        with pytest.raises(AssertionError):
            hasher.encode("password", "salt$with$dollar")

    @patch("src.modules.auth.hashers.hmac.compare_digest")
    def test_verify_timing_attack_protection(
        self, mock_compare_digest: MagicMock, hasher: PBKDF2PasswordHasher
    ) -> None:
        """Test that verification uses timing attack protected comparison."""
        password = "test-password"
        encoded = hasher.encode(password)

        hasher.verify(password, encoded)

        # Verify that hmac.compare_digest was called
        mock_compare_digest.assert_called_once()

    def test_pbkdf2_internal_method(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test internal _pbkdf2 method."""
        password = "test-password"
        salt = "test-salt"

        result = hasher._pbkdf2(password, salt)

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_pbkdf2_consistency(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test that _pbkdf2 produces consistent results."""
        password = "test-password"
        salt = "test-salt"

        result1 = hasher._pbkdf2(password, salt)
        result2 = hasher._pbkdf2(password, salt)

        assert result1 == result2

    def test_pbkdf2_different_inputs(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test that _pbkdf2 produces different results for different inputs."""
        password1 = "password1"
        password2 = "password2"
        salt = "test-salt"

        result1 = hasher._pbkdf2(password1, salt)
        result2 = hasher._pbkdf2(password2, salt)

        assert result1 != result2
