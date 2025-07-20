"""Tests for authentication tokens module."""

import datetime
import pytest
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from pydantic import SecretStr

from src.modules.auth.tokens import (
    JWTPayload,
    jwt_encode,
    jwt_decode,
    make_api_token,
    decode_api_token,
    hash_token,
    verify_api_token,
    GeneratedToken,
)
from src.settings import AppSettings
from src.db.models import Token, User


# Module-level fixtures
@pytest.fixture
def test_settings() -> AppSettings:
    """Return test settings with secret key."""
    return AppSettings(
        api_token=SecretStr("test-token"),
        admin_username="test-username",
        admin_password=SecretStr("test-password"),
        secret_key=SecretStr("test-secret-key-for-jwt-encoding"),
        jwt_algorithm="HS256",
    )


@pytest.fixture
def mock_user() -> User:
    """Return mock user object."""
    user = MagicMock(spec=User)
    user.is_active = True
    return user


@pytest.fixture
def mock_token(mock_user: User) -> Token:
    """Return mock token object."""
    token = MagicMock(spec=Token)
    token.is_active = True
    token.user = mock_user
    return token


@pytest.fixture
def mock_session_uow() -> Tuple[MagicMock, AsyncMock]:
    """Mock SASessionUOW context manager."""
    with patch("src.modules.auth.tokens.SASessionUOW") as mock_uow:
        mock_session = AsyncMock()
        mock_uow.return_value.__aenter__.return_value.session = mock_session
        yield mock_uow, mock_session


@pytest.fixture
def mock_token_repository(mock_token: Token) -> Tuple[MagicMock, AsyncMock]:
    """Mock TokenRepository with active token."""
    with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_token_repository_inactive_token(mock_user: User) -> Tuple[MagicMock, AsyncMock]:
    """Mock TokenRepository with inactive token."""
    with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_token = MagicMock()
        mock_token.is_active = False
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_token_repository_inactive_user(mock_user: User) -> Tuple[MagicMock, AsyncMock]:
    """Mock TokenRepository with inactive user."""
    with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_token = MagicMock()
        mock_token.is_active = True
        mock_token.user.is_active = False
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_token_repository_unknown_token() -> Tuple[MagicMock, AsyncMock]:
    """Mock TokenRepository with unknown token."""
    with patch("src.modules.auth.tokens.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.get_by_token.return_value = None
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


class TestJWTPayload:
    """Tests for JWTPayload dataclass."""

    def test_jwt_payload_creation(self) -> None:
        """Test JWTPayload creation with basic parameters."""
        payload = JWTPayload(sub="test-user")
        assert payload.sub == "test-user"
        assert payload.exp is None

    def test_jwt_payload_with_expiration(self) -> None:
        """Test JWTPayload creation with expiration time."""
        exp_time = datetime.datetime.now() + datetime.timedelta(hours=1)
        payload = JWTPayload(sub="test-user", exp=exp_time)
        assert payload.sub == "test-user"
        assert payload.exp == exp_time

    def test_jwt_payload_as_dict(self) -> None:
        """Test JWTPayload conversion to dictionary."""
        exp_time = datetime.datetime.now() + datetime.timedelta(hours=1)
        payload = JWTPayload(sub="test-user", exp=exp_time)
        payload_dict = payload.as_dict()

        assert payload_dict["sub"] == "test-user"
        assert payload_dict["exp"] == exp_time


class TestJWTEncodeDecode:
    """Tests for JWT encoding and decoding functions."""

    def test_jwt_encode_basic(self, test_settings: AppSettings) -> None:
        """Test basic JWT encoding."""
        payload = JWTPayload(sub="test-user")
        token = jwt_encode(payload, test_settings)

        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # header.payload.signature

    def test_jwt_encode_with_expiration(self, test_settings: AppSettings) -> None:
        """Test JWT encoding with expiration time."""
        exp_time = datetime.datetime.now() + datetime.timedelta(hours=1)
        payload = JWTPayload(sub="test-user")
        token = jwt_encode(payload, test_settings, expires_at=exp_time)

        # Decode to verify expiration was set
        decoded = jwt_decode(token, test_settings)
        assert decoded.sub == "test-user"
        assert decoded.exp is not None

    def test_jwt_decode_valid_token(self, test_settings: AppSettings) -> None:
        """Test JWT decoding of valid token."""
        payload = JWTPayload(sub="test-user")
        token = jwt_encode(payload, test_settings)
        decoded = jwt_decode(token, test_settings)

        assert decoded.sub == "test-user"

    def test_jwt_decode_invalid_token(self, test_settings: AppSettings) -> None:
        """Test JWT decoding of invalid token."""
        with pytest.raises(Exception):  # jwt.InvalidTokenError
            jwt_decode("invalid.token.here", test_settings)


class TestMakeAPIToken:
    """Tests for API token generation."""

    def test_make_api_token_basic(self, test_settings: AppSettings) -> None:
        """Test basic API token generation."""
        result = make_api_token(expires_at=None, settings=test_settings)

        assert isinstance(result, GeneratedToken)
        assert isinstance(result.value, str)
        assert isinstance(result.hashed_value, str)
        assert len(result.value) > 0
        assert len(result.hashed_value) > 0

    def test_make_api_token_with_expiration(self, test_settings: AppSettings) -> None:
        """Test API token generation with expiration time."""
        exp_time = datetime.datetime.now() + datetime.timedelta(hours=1)
        result = make_api_token(expires_at=exp_time, settings=test_settings)

        # Token should be decodable
        decoded = decode_api_token(result.value, test_settings)
        assert decoded.exp is not None
        assert decoded.exp == exp_time

    def test_make_api_token_custom_format(self, test_settings: AppSettings) -> None:
        """Test that generated token has custom format (no header, length prefix)."""
        result = make_api_token(expires_at=None, settings=test_settings)

        # Token should not contain dots (no header)
        assert "." not in result.value

        # Last 3 characters should be numeric (length prefix)
        length_prefix = result.value[-3:]
        assert length_prefix.isnumeric()

        # Token should be longer than just the length prefix
        assert len(result.value) > 3


class TestDecodeAPIToken:
    """Tests for API token decoding."""

    def test_decode_api_token_valid(self, test_settings: AppSettings) -> None:
        """Test decoding of valid API token."""
        # Generate a token first
        generated = make_api_token(expires_at=None, settings=test_settings)

        # Decode it
        decoded = decode_api_token(generated.value, test_settings)

        assert isinstance(decoded, JWTPayload)
        assert decoded.sub is not None
        assert len(decoded.sub) > 0

    def test_decode_api_token_invalid_length_prefix(self, test_settings: AppSettings) -> None:
        """Test decoding with invalid length prefix."""
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token("invalidtoken", test_settings)

        assert exc_info.value.status_code == 401
        assert "Invalid token signature" in str(exc_info.value.detail)

    def test_decode_api_token_expired(self, test_settings: AppSettings) -> None:
        """Test decoding of expired token."""
        # Generate token with past expiration
        past_time = datetime.datetime.now() - datetime.timedelta(hours=1)
        generated = make_api_token(expires_at=past_time, settings=test_settings)

        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(generated.value, test_settings)

        assert exc_info.value.status_code == 401
        assert "Token expired" in str(exc_info.value.detail)

    def test_decode_api_token_malformed(self, test_settings: AppSettings) -> None:
        """Test decoding of malformed token."""
        with pytest.raises(HTTPException) as exc_info:
            decode_api_token("malformed123", test_settings)

        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)

    def test_decode_api_token_no_expiration(self, test_settings: AppSettings) -> None:
        """Test decoding token without expiration (should fail)."""
        # Create a token without expiration by mocking jwt_encode
        with patch("src.modules.auth.tokens.jwt_encode") as mock_encode:
            mock_encode.return_value = "header.payload.signature"
            generated = make_api_token(expires_at=None, settings=test_settings)

        with pytest.raises(HTTPException) as exc_info:
            decode_api_token(generated.value, test_settings)

        assert exc_info.value.status_code == 401
        assert "Token has no expiration time" in str(exc_info.value.detail)


class TestHashToken:
    """Tests for token hashing function."""

    def test_hash_token_basic(self) -> None:
        """Test basic token hashing."""
        token = "test-token-123"
        hashed = hash_token(token)

        assert isinstance(hashed, str)
        assert len(hashed) == 128  # SHA-512 hex digest length
        assert hashed != token

    def test_hash_token_consistency(self) -> None:
        """Test that same token always produces same hash."""
        token = "test-token-123"
        hash1 = hash_token(token)
        hash2 = hash_token(token)

        assert hash1 == hash2

    def test_hash_token_different_tokens(self) -> None:
        """Test that different tokens produce different hashes."""
        token1 = "test-token-123"
        token2 = "test-token-456"

        hash1 = hash_token(token1)
        hash2 = hash_token(token2)

        assert hash1 != hash2

    def test_hash_token_empty_string(self) -> None:
        """Test hashing empty string."""
        hashed = hash_token("")

        assert isinstance(hashed, str)
        assert len(hashed) == 128


class TestVerifyAPIToken:
    """Tests for API token verification dependency."""

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        """Return mock request object."""
        request = MagicMock()
        request.method = "GET"
        return request

    @pytest.mark.asyncio
    async def test_verify_api_token_options_method(
        self, test_settings: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test that OPTIONS method skips verification."""
        mock_request.method = "OPTIONS"

        result = await verify_api_token(mock_request, test_settings, auth_token=None)

        assert result == ""

    @pytest.mark.asyncio
    async def test_verify_api_token_no_token(
        self, test_settings: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification without token."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token=None)

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_with_bearer_prefix(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with Bearer prefix in token."""
        # Generate valid token
        generated = make_api_token(expires_at=None, settings=test_settings)
        auth_token = f"Bearer {generated.value}"

        result = await verify_api_token(mock_request, test_settings, auth_token=auth_token)

        assert result == auth_token

    @pytest.mark.asyncio
    async def test_verify_api_token_inactive_token(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_inactive_token: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with inactive token."""
        generated = make_api_token(expires_at=None, settings=test_settings)
        auth_token = f"Bearer {generated.value}"

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token=auth_token)

        assert exc_info.value.status_code == 401
        assert "inactive token" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_inactive_user(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_inactive_user: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with inactive user."""
        generated = make_api_token(expires_at=None, settings=test_settings)
        auth_token = f"Bearer {generated.value}"

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token=auth_token)

        assert exc_info.value.status_code == 401
        assert "user is not active" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_unknown_token(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_unknown_token: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with unknown token."""
        generated = make_api_token(expires_at=None, settings=test_settings)
        auth_token = f"Bearer {generated.value}"

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token=auth_token)

        assert exc_info.value.status_code == 401
        assert "unknown token" in str(exc_info.value.detail)
