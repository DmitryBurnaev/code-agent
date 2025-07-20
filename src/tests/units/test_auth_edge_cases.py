"""Edge cases and special scenarios tests for authentication module."""

import datetime
import pytest
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from pydantic import SecretStr

from src.modules.auth.tokens import (
    make_api_token,
    decode_api_token,
    hash_token,
    verify_api_token,
    JWTPayload,
    jwt_encode,
    jwt_decode,
)
from src.modules.auth.hashers import (
    PBKDF2PasswordHasher,
    get_salt,
    get_random_hash,
)
from src.settings import AppSettings


# Module-level fixtures
@pytest.fixture
def test_settings() -> AppSettings:
    """Return test settings."""
    return AppSettings(
        api_token=SecretStr("test-token"),
        admin_username="test-username",
        admin_password=SecretStr("test-password"),
        secret_key=SecretStr("test-secret-key-for-edge-cases"),
        jwt_algorithm="HS256",
    )


@pytest.fixture
def mock_request() -> MagicMock:
    """Return mock request object."""
    request = MagicMock()
    request.method = "GET"
    return request


@pytest.fixture
def mock_make_token() -> MagicMock:
    """Mock make_api_token function."""
    with patch("src.modules.auth.dependencies.make_api_token") as mock:
        mock.return_value = MagicMock(value="test-token-value", hashed_value="test-hash")
        yield mock


@pytest.fixture
def mock_decode_token() -> MagicMock:
    """Mock decode_api_token function."""
    with patch("src.modules.auth.dependencies.decode_api_token") as mock:
        mock.return_value = MagicMock(sub="test-user-id")
        yield mock


@pytest.fixture
def mock_hash_token() -> MagicMock:
    """Mock hash_token function."""
    with patch("src.modules.auth.dependencies.hash_token") as mock:
        mock.return_value = "test-hash"
        yield mock


@pytest.fixture
def mock_session_uow() -> Tuple[MagicMock, AsyncMock]:
    """Mock SASessionUOW context manager."""
    with patch("src.modules.auth.dependencies.SASessionUOW") as mock_uow:
        mock_session = AsyncMock()
        mock_uow.return_value.__aenter__.return_value.session = mock_session
        yield mock_uow, mock_session


@pytest.fixture
def mock_token_repository_active() -> Tuple[MagicMock, AsyncMock]:
    """Mock TokenRepository with active token and user."""
    with patch("src.modules.auth.dependencies.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_token = MagicMock()
        mock_token.is_active = True
        mock_token.user.is_active = True
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


class TestTokenEdgeCases:
    """Tests for token edge cases and special scenarios."""

    def test_token_with_empty_secret_key(self) -> None:
        """Test token generation with empty secret key."""
        empty_settings = AppSettings(
            api_token=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr(""),
            jwt_algorithm="HS256",
        )

        # Should still work with empty secret key
        generated = make_api_token(expires_at=None, settings=empty_settings)
        decoded = decode_api_token(generated.value, empty_settings)

        assert decoded.sub is not None

    def test_token_with_very_long_secret_key(self) -> None:
        """Test token generation with very long secret key."""
        long_secret = "a" * 1000  # Very long secret key
        long_settings = AppSettings(
            api_token=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr(long_secret),
            jwt_algorithm="HS256",
        )

        generated = make_api_token(expires_at=None, settings=long_settings)
        decoded = decode_api_token(generated.value, long_settings)

        assert decoded.sub is not None

    def test_token_with_special_characters_in_secret(self) -> None:
        """Test token generation with special characters in secret key."""
        special_secret = "!@#$%^&*()_+-=[]{}|;:,.<>?`~"
        special_settings = AppSettings(
            api_token=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr(special_secret),
            jwt_algorithm="HS256",
        )

        generated = make_api_token(expires_at=None, settings=special_settings)
        decoded = decode_api_token(generated.value, special_settings)

        assert decoded.sub is not None

    def test_token_with_unicode_secret_key(self) -> None:
        """Test token generation with unicode characters in secret key."""
        unicode_secret = "секретный-ключ-с-юникодом-тест"
        unicode_settings = AppSettings(
            api_token=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr(unicode_secret),
            jwt_algorithm="HS256",
        )

        generated = make_api_token(expires_at=None, settings=unicode_settings)
        decoded = decode_api_token(generated.value, unicode_settings)

        assert decoded.sub is not None

    def test_token_with_minimal_expiration(self, test_settings: AppSettings) -> None:
        """Test token with minimal expiration time."""
        minimal_exp = datetime.datetime.now() + datetime.timedelta(microseconds=1)
        generated = make_api_token(expires_at=minimal_exp, settings=test_settings)

        # Should be decodable immediately
        decoded = decode_api_token(generated.value, test_settings)
        assert decoded.exp == minimal_exp

    def test_token_with_maximum_expiration(self, test_settings: AppSettings) -> None:
        """Test token with maximum expiration time."""
        max_exp = datetime.datetime.max
        generated = make_api_token(expires_at=max_exp, settings=test_settings)

        decoded = decode_api_token(generated.value, test_settings)
        assert decoded.exp == max_exp

    def test_token_with_negative_expiration(self, test_settings: AppSettings) -> None:
        """Test token with negative expiration time (past time)."""
        past_time = datetime.datetime.now() - datetime.timedelta(hours=1)
        generated = make_api_token(expires_at=past_time, settings=test_settings)

        # Should raise exception when decoding
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(generated.value, test_settings)

        assert exc_info.value.status_code == 401
        assert "Token expired" in str(exc_info.value.detail)

    def test_token_with_exactly_current_time_expiration(self, test_settings: AppSettings) -> None:
        """Test token with expiration exactly at current time."""
        current_time = datetime.datetime.now()
        generated = make_api_token(expires_at=current_time, settings=test_settings)

        # Should raise exception when decoding (expired)
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(generated.value, test_settings)

        assert exc_info.value.status_code == 401
        assert "Token expired" in str(exc_info.value.detail)

    def test_token_with_very_short_token_string(self, test_settings: AppSettings) -> None:
        """Test decoding with very short token string."""
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token("123", test_settings)

        assert exc_info.value.status_code == 401

    def test_token_with_non_numeric_length_prefix(self, test_settings: AppSettings) -> None:
        """Test decoding with non-numeric length prefix."""
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token("payloadsignatureabc", test_settings)

        assert exc_info.value.status_code == 401
        assert "Invalid token signature" in str(exc_info.value.detail)

    def test_token_with_invalid_length_prefix(self, test_settings: AppSettings) -> None:
        """Test decoding with invalid length prefix."""
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token("payloadsignature999", test_settings)

        assert exc_info.value.status_code == 401

    def test_token_with_malformed_payload(self, test_settings: AppSettings) -> None:
        """Test decoding with malformed payload."""
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token("invalidpayload123", test_settings)

        assert exc_info.value.status_code == 401

    def test_token_with_wrong_signature_length(self, test_settings: AppSettings) -> None:
        """Test decoding with wrong signature length."""
        # Create a token with wrong signature length in prefix
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token("payloadsignature001", test_settings)

        assert exc_info.value.status_code == 401

    def test_hash_token_with_empty_string(self) -> None:
        """Test hashing empty string."""
        hashed = hash_token("")

        assert isinstance(hashed, str)
        assert len(hashed) == 128  # SHA-512 hex digest length

    def test_hash_token_with_very_long_string(self) -> None:
        """Test hashing very long string."""
        long_string = "a" * 10000
        hashed = hash_token(long_string)

        assert isinstance(hashed, str)
        assert len(hashed) == 128

    def test_hash_token_with_unicode_string(self) -> None:
        """Test hashing unicode string."""
        unicode_string = "тест-строка-с-юникодом-测试字符串"
        hashed = hash_token(unicode_string)

        assert isinstance(hashed, str)
        assert len(hashed) == 128

    def test_hash_token_with_special_characters(self) -> None:
        """Test hashing string with special characters."""
        special_string = "!@#$%^&*()_+-=[]{}|;:,.<>?`~"
        hashed = hash_token(special_string)

        assert isinstance(hashed, str)
        assert len(hashed) == 128

    def test_hash_token_with_binary_like_string(self) -> None:
        """Test hashing string that looks like binary data."""
        binary_like = "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09"
        hashed = hash_token(binary_like)

        assert isinstance(hashed, str)
        assert len(hashed) == 128


class TestPasswordHasherEdgeCases:
    """Tests for password hasher edge cases."""

    @pytest.fixture
    def hasher(self) -> PBKDF2PasswordHasher:
        """Return PBKDF2PasswordHasher instance."""
        return PBKDF2PasswordHasher()

    def test_encode_empty_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test encoding empty password."""
        encoded = hasher.encode("")

        assert isinstance(encoded, str)
        assert encoded.startswith("pbkdf2_sha256$")

    def test_encode_very_long_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test encoding very long password."""
        long_password = "a" * 10000
        encoded = hasher.encode(long_password)

        assert isinstance(encoded, str)
        assert encoded.startswith("pbkdf2_sha256$")

    def test_encode_unicode_password(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test encoding unicode password."""
        unicode_password = "тест-пароль-с-юникодом-测试密码"
        encoded = hasher.encode(unicode_password)

        assert isinstance(encoded, str)
        assert encoded.startswith("pbkdf2_sha256$")

    def test_encode_password_with_special_characters(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test encoding password with special characters."""
        special_password = "!@#$%^&*()_+-=[]{}|;:,.<>?`~"
        encoded = hasher.encode(special_password)

        assert isinstance(encoded, str)
        assert encoded.startswith("pbkdf2_sha256$")

    def test_encode_password_with_null_bytes(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test encoding password with null bytes."""
        null_password = "password\x00with\x00nulls"
        encoded = hasher.encode(null_password)

        assert isinstance(encoded, str)
        assert encoded.startswith("pbkdf2_sha256$")

    def test_verify_empty_password_against_empty_encoded(
        self, hasher: PBKDF2PasswordHasher
    ) -> None:
        """Test verifying empty password against empty encoded password."""
        encoded = hasher.encode("")
        is_valid, message = hasher.verify("", encoded)

        assert is_valid is True
        assert message == ""

    def test_verify_wrong_password_against_empty_encoded(
        self, hasher: PBKDF2PasswordHasher
    ) -> None:
        """Test verifying wrong password against empty encoded password."""
        encoded = hasher.encode("")
        is_valid, message = hasher.verify("wrong", encoded)

        assert is_valid is False
        assert message == ""

    def test_verify_empty_password_against_normal_encoded(
        self, hasher: PBKDF2PasswordHasher
    ) -> None:
        """Test verifying empty password against normal encoded password."""
        encoded = hasher.encode("normal-password")
        is_valid, message = hasher.verify("", encoded)

        assert is_valid is False
        assert message == ""

    def test_verify_with_malformed_encoded_password_missing_parts(
        self, hasher: PBKDF2PasswordHasher
    ) -> None:
        """Test verifying with malformed encoded password missing parts."""
        password = "test-password"
        malformed_encoded = "pbkdf2_sha256$180000$salt"  # Missing hash part

        is_valid, message = hasher.verify(password, malformed_encoded)

        assert is_valid is False
        assert "incompatible format" in message

    def test_verify_with_malformed_encoded_password_extra_parts(
        self, hasher: PBKDF2PasswordHasher
    ) -> None:
        """Test verifying with malformed encoded password with extra parts."""
        password = "test-password"
        malformed_encoded = "pbkdf2_sha256$180000$salt$hash$extra"

        is_valid, message = hasher.verify(password, malformed_encoded)

        assert is_valid is False
        assert "incompatible format" in message

    def test_verify_with_wrong_iterations(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verifying with wrong iterations in encoded password."""
        password = "test-password"
        wrong_iterations_encoded = "pbkdf2_sha256$999999$salt$hash"

        is_valid, message = hasher.verify(password, wrong_iterations_encoded)

        assert is_valid is False
        assert message == ""

    def test_verify_with_non_numeric_iterations(self, hasher: PBKDF2PasswordHasher) -> None:
        """Test verifying with non-numeric iterations in encoded password."""
        password = "test-password"
        non_numeric_iterations_encoded = "pbkdf2_sha256$invalid$salt$hash"

        is_valid, message = hasher.verify(password, non_numeric_iterations_encoded)

        assert is_valid is False
        assert "incompatible format" in message

    def test_salt_generation_edge_cases(self) -> None:
        """Test salt generation edge cases."""
        # Test with zero length
        salt_zero = get_salt(length=0)
        assert salt_zero == ""

        # Test with very long length
        salt_long = get_salt(length=100)
        assert len(salt_long) == 100
        assert salt_long.isalnum()

    def test_random_hash_edge_cases(self) -> None:
        """Test random hash generation edge cases."""
        # Test with zero size
        hash_zero = get_random_hash(size=0)
        assert hash_zero == ""

        # Test with very large size
        hash_large = get_random_hash(size=1000)
        assert len(hash_large) == 1000
        assert all(c in "0123456789abcdef" for c in hash_large)


class TestAuthDependencyEdgeCases:
    """Tests for authentication dependency edge cases."""

    @pytest.mark.asyncio
    async def test_verify_api_token_with_whitespace_only_token(
        self, test_settings: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification with whitespace-only token."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="   ")

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_with_tab_characters(
        self, test_settings: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification with token containing tab characters."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="\tBearer\t")

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_with_newline_characters(
        self, test_settings: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification with token containing newline characters."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="Bearer\n")

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_with_unicode_whitespace(
        self, test_settings: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification with token containing unicode whitespace."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(
                mock_request, test_settings, auth_token="\u2003Bearer\u2003"
            )  # Em space

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_with_case_insensitive_bearer(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_make_token: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_active: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with case-insensitive Bearer prefix."""
        # Test with lowercase bearer
        auth_token = "bearer test-token-value"
        result = await verify_api_token(mock_request, test_settings, auth_token=auth_token)

        assert result == auth_token

    @pytest.mark.asyncio
    async def test_verify_api_token_with_mixed_case_bearer(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_make_token: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_active: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with mixed case Bearer prefix."""
        # Test with mixed case bearer
        auth_token = "BeArEr test-token-value"
        result = await verify_api_token(mock_request, test_settings, auth_token=auth_token)

        assert result == auth_token
