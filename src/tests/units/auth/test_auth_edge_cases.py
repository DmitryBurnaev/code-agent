"""Edge cases and special scenarios tests for authentication module."""

import datetime
import pytest
from typing import Any, Generator, NamedTuple
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from pydantic import SecretStr

from src.modules.auth.tokens import (
    make_api_token,
    decode_api_token,
    hash_token,
    verify_api_token,
)
from src.modules.auth.hashers import (
    PBKDF2PasswordHasher,
    get_salt,
    get_random_hash,
)
from src.settings import AppSettings
from src.tests.units.auth.conftest import GenMockPair
from src.utils import utcnow


@pytest.fixture
def mock_request() -> MagicMock:
    """Return mock request object."""
    request = MagicMock()
    request.method = "GET"
    return request


@pytest.fixture
def mock_make_token() -> Generator[MagicMock, Any, None]:
    """Mock make_api_token function."""
    with patch("src.modules.auth.dependencies.make_api_token") as mock:
        mock.return_value = MagicMock(value="test-token-value", hashed_value="test-hash")
        yield mock


@pytest.fixture
def mock_decode_token() -> Generator[MagicMock, Any, None]:
    """Mock decode_api_token function."""
    with patch("src.modules.auth.dependencies.decode_api_token") as mock:
        mock.return_value = MagicMock(sub="test-user-id")
        yield mock


@pytest.fixture
def mock_hash_token() -> Generator[MagicMock, Any, None]:
    """Mock hash_token function."""
    with patch("src.modules.auth.dependencies.hash_token") as mock:
        mock.return_value = "test-hash"
        yield mock


@pytest.fixture
def mock_session_uow() -> GenMockPair:
    """Mock SASessionUOW context manager."""
    with patch("src.modules.auth.dependencies.SASessionUOW") as mock_uow:
        mock_session = AsyncMock()
        mock_uow.return_value.__aenter__.return_value.session = mock_session
        yield mock_uow, mock_session


@pytest.fixture
def mock_token_repository_active() -> GenMockPair:
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

    @pytest.mark.parametrize(
        "secret_key",
        (
            "",
            "a" * 1000,
            "!@#$%^&*()_+-=[]{}|;:,.<>?`~",
            "секретный-ключ",
        ),
        ids=(
            "empty",
            "long",
            "special-characters",
            "unicode",
        ),
    )
    def test_token_with_various_secret_key(self, secret_key: str) -> None:
        app_settings = AppSettings(
            api_token=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr(secret_key),
            vendor_encryption_key=SecretStr(""),
            jwt_algorithm="HS256",
        )

        generated = make_api_token(expires_at=None, settings=app_settings)
        assert isinstance(generated, NamedTuple)
        assert isinstance(generated.value, str)
        assert isinstance(generated.hashed_value, str)

        decoded = decode_api_token(generated.value, app_settings)
        assert decoded.sub is not None

    def test_token_with_minimal_expiration(self, app_settings_test: AppSettings) -> None:
        minimal_exp = utcnow(skip_tz=False) + datetime.timedelta(microseconds=1)
        generated = make_api_token(expires_at=minimal_exp, settings=app_settings_test)

        # Should be decodable immediately
        decoded = decode_api_token(generated.value, app_settings_test)
        assert decoded.exp == minimal_exp

    def test_token_with_maximum_expiration(self, app_settings_test: AppSettings) -> None:
        max_exp = datetime.datetime.max
        generated = make_api_token(expires_at=max_exp, settings=app_settings_test)

        decoded = decode_api_token(generated.value, app_settings_test)
        assert decoded.exp == max_exp

    def test_token_with_negative_expiration(self, app_settings_test: AppSettings) -> None:
        past_time = utcnow(skip_tz=False) - datetime.timedelta(hours=1)
        generated = make_api_token(expires_at=past_time, settings=app_settings_test)

        # Should raise exception when decoding
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(generated.value, app_settings_test)

        assert exc_info.value.status_code == 401
        assert "Token expired" in str(exc_info.value.detail)

    def test_token_with_exactly_current_time_expiration(
        self, app_settings_test: AppSettings
    ) -> None:
        current_time = utcnow(skip_tz=False)
        generated = make_api_token(expires_at=current_time, settings=app_settings_test)

        # Should raise exception when decoding (expired)
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(generated.value, app_settings_test)

        assert exc_info.value.status_code == 401
        assert "Token expired" in str(exc_info.value.detail)

    @pytest.mark.parametrize(
        "token_string,expected_detail_contains",
        [
            ("123", None),  # Very short token
            ("payload-signature-abc", "Invalid token signature"),  # Non-numeric length prefix
            ("payload-signature999", None),  # Invalid length prefix
            ("invalid-payload123", None),  # Malformed payload
            ("payload-signature001", None),  # Wrong signature length
        ],
        ids=[
            "very_short_token",
            "non_numeric_length_prefix",
            "invalid_length_prefix",
            "malformed_payload",
            "wrong_signature_length",
        ],
    )
    def test_token_with_malformed_inputs(
        self,
        app_settings_test: AppSettings,
        token_string: str,
        expected_detail_contains: str | None,
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(token_string, app_settings_test)

        assert exc_info.value.status_code == 401

        if expected_detail_contains:
            assert expected_detail_contains in str(exc_info.value.detail)

    @pytest.mark.parametrize(
        "input_string,description",
        [
            ("", "empty string"),
            ("a" * 10000, "very long string"),
            ("тест-строка-测试字符串", "unicode string"),
            ("!@#$%^&*()_+-=[]{}|;:,.<>?`~", "special characters"),
            ("\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09", "binary-like string"),
        ],
        ids=[
            "empty_string",
            "very_long_string",
            "unicode_string",
            "special_characters",
            "binary_like_string",
        ],
    )
    def test_hash_token_edge_cases(self, input_string: str, description: str) -> None:
        hashed = hash_token(input_string)

        assert isinstance(hashed, str)
        assert len(hashed) == 128  # SHA-512 hex digest length


class TestPasswordHasherEdgeCases:
    """Tests for password hasher edge cases."""

    @pytest.fixture
    def hasher(self) -> PBKDF2PasswordHasher:
        """Return PBKDF2PasswordHasher instance."""
        return PBKDF2PasswordHasher()

    @pytest.mark.parametrize(
        "password,description",
        [
            ("", "empty password"),
            ("a" * 10000, "very long password"),
            ("тест-пароль-с-юникодом-测试密码", "unicode password"),
            ("!@#$%^&*()_+-=[]{}|;:,.<>?`~", "special characters"),
            ("password\x00with\x00nulls", "null bytes"),
        ],
        ids=[
            "empty_password",
            "very_long_password",
            "unicode_password",
            "special_characters",
            "null_bytes",
        ],
    )
    def test_encode_password_edge_cases(
        self, hasher: PBKDF2PasswordHasher, password: str, description: str
    ) -> None:
        encoded = hasher.encode(password)

        assert isinstance(encoded, str)
        assert encoded.startswith("pbkdf2_sha256$")

    @pytest.mark.parametrize(
        "password,encoded_password,expected_valid,expected_message_contains,description",
        [
            ("", None, True, "", "empty password against empty encoded"),
            ("wrong", None, False, "", "wrong password against empty encoded"),
            ("", "normal-password-encoded", False, "", "empty password against normal encoded"),
            (
                "test-password",
                "pbkdf2_sha256$180000$salt",
                False,
                "incompatible format",
                "missing hash part",
            ),
            (
                "test-password",
                "pbkdf2_sha256$180000$salt$hash$extra",
                False,
                "incompatible format",
                "extra parts",
            ),
            ("test-password", "pbkdf2_sha256$999999$salt$hash", False, "", "wrong iterations"),
            (
                "test-password",
                "pbkdf2_sha256$invalid$salt$hash",
                False,
                "incompatible format",
                "non-numeric iterations",
            ),
        ],
        ids=[
            "empty_vs_empty",
            "wrong_vs_empty",
            "empty_vs_normal",
            "missing_hash_part",
            "extra_parts",
            "wrong_iterations",
            "non_numeric_iterations",
        ],
    )
    def test_verify_password_edge_cases(
        self,
        hasher: PBKDF2PasswordHasher,
        password: str,
        encoded_password: str | None,
        expected_valid: bool,
        expected_message_contains: str,
        description: str,
    ) -> None:
        if encoded_password is None:
            # For tests that need to encode empty password first
            encoded = hasher.encode("")
        else:
            encoded = encoded_password

        is_valid, message = hasher.verify(password, encoded)

        assert is_valid is expected_valid
        if expected_message_contains:
            assert expected_message_contains in message
        else:
            assert message == ""

    @pytest.mark.parametrize(
        "length,expected_length,description",
        [
            (0, 0, "zero length"),
            (100, 100, "very long length"),
        ],
        ids=[
            "zero_length",
            "very_long_length",
        ],
    )
    def test_salt_generation_edge_cases(
        self, length: int, expected_length: int, description: str
    ) -> None:
        salt = get_salt(length=length)

        if expected_length == 0:
            assert salt == ""
        else:
            assert len(salt) == expected_length
            assert salt.isalnum()

    @pytest.mark.parametrize(
        "size,expected_size,description",
        [
            (0, 0, "zero size"),
            (1000, 1000, "very large size"),
        ],
        ids=[
            "zero_size",
            "very_large_size",
        ],
    )
    def test_random_hash_edge_cases(self, size: int, expected_size: int, description: str) -> None:
        hash_result = get_random_hash(size=size)

        if expected_size == 0:
            assert hash_result == ""
        else:
            assert len(hash_result) == expected_size
            assert all(c in "0123456789abcdef" for c in hash_result)


class TestAuthDependencyEdgeCases:
    """Tests for authentication dependency edge cases."""

    @pytest.mark.parametrize(
        "auth_token,should_raise,expected_detail_contains,description",
        [
            ("   ", True, "Not authenticated", "whitespace only token"),
            ("\tBearer\t", True, "Not authenticated", "tab characters"),
            ("Bearer\n", True, "Not authenticated", "newline characters"),
            ("\u2003Bearer\u2003", True, "Not authenticated", "unicode whitespace"),
        ],
        ids=[
            "whitespace_only",
            "tab_characters",
            "newline_characters",
            "unicode_whitespace",
        ],
    )
    @pytest.mark.asyncio
    async def test_verify_api_token_with_whitespace_edge_cases(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        auth_token: str,
        should_raise: bool,
        expected_detail_contains: str,
        description: str,
    ) -> None:
        if should_raise:
            with pytest.raises(HTTPException) as exc_info:
                await verify_api_token(mock_request, app_settings_test, auth_token=auth_token)

            assert exc_info.value.status_code == 401
            assert expected_detail_contains in str(exc_info.value.detail)

    @pytest.mark.parametrize(
        "auth_token,description",
        [
            ("bearer test-token-value", "lowercase bearer"),
            ("BeArEr test-token-value", "mixed case bearer"),
        ],
        ids=[
            "lowercase_bearer",
            "mixed_case_bearer",
        ],
    )
    @pytest.mark.asyncio
    async def test_verify_api_token_with_case_insensitive_bearer(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_make_token: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow: GenMockPair,
        mock_token_repository_active: GenMockPair,
        auth_token: str,
        description: str,
    ) -> None:
        result = await verify_api_token(mock_request, app_settings_test, auth_token=auth_token)

        assert result == auth_token
