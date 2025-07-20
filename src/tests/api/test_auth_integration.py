"""Integration tests for authentication module."""

import datetime
import pytest
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.main import make_app
from src.settings import AppSettings, get_app_settings
from src.modules.auth.tokens import make_api_token, decode_api_token, hash_token
from src.db.models import Token, User


# Module-level fixtures
@pytest.fixture
def test_settings() -> AppSettings:
    """Return test settings for integration tests."""
    return AppSettings(
        api_token=SecretStr("test-token"),
        admin_username="test-username",
        admin_password=SecretStr("test-password"),
        secret_key=SecretStr("test-secret-key-for-integration-tests"),
        jwt_algorithm="HS256",
    )


@pytest.fixture
def test_app(test_settings: AppSettings) -> FastAPI:
    """Return FastAPI app with test settings."""
    app = make_app(settings=test_settings)
    app.dependency_overrides[get_app_settings] = lambda: test_settings
    return app


@pytest.fixture
def test_client(test_app: FastAPI) -> TestClient:
    """Return test client."""
    return TestClient(test_app)


@pytest.fixture
def mock_user() -> User:
    """Return mock user for testing."""
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "test-user"
    user.is_active = True
    return user


@pytest.fixture
def mock_token(mock_user: User) -> Token:
    """Return mock token for testing."""
    token = MagicMock(spec=Token)
    token.id = 1
    token.token_hash = "test-hash"
    token.is_active = True
    token.user = mock_user
    return token


@pytest.fixture
def mock_session_uow() -> Tuple[MagicMock, AsyncMock]:
    """Mock SASessionUOW context manager."""
    with patch("src.modules.auth.dependencies.SASessionUOW") as mock_uow:
        mock_session = AsyncMock()
        mock_uow.return_value.__aenter__.return_value.session = mock_session
        yield mock_uow, mock_session


@pytest.fixture
def mock_token_repository(mock_token: Token) -> Tuple[MagicMock, AsyncMock]:
    """Mock TokenRepository with active token."""
    with patch("src.modules.auth.dependencies.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


class TestAuthIntegration:
    """Integration tests for authentication flow."""

    def test_full_token_lifecycle(self, test_settings: AppSettings) -> None:
        """Test complete token lifecycle: generation -> decoding -> verification."""
        # Step 1: Generate token
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=1)
        generated = make_api_token(expires_at=expires_at, settings=test_settings)

        assert isinstance(generated.value, str)
        assert isinstance(generated.hashed_value, str)
        assert len(generated.value) > 0
        assert len(generated.hashed_value) > 0

        # Step 2: Decode token
        decoded = decode_api_token(generated.value, test_settings)

        assert decoded.sub is not None
        assert decoded.exp is not None
        assert decoded.exp == expires_at

        # Step 3: Verify token hash
        expected_hash = hash_token(decoded.sub)
        assert generated.hashed_value == expected_hash

    def test_token_format_consistency(self, test_settings: AppSettings) -> None:
        """Test that token format is consistent across multiple generations."""
        tokens = []

        for _ in range(5):
            generated = make_api_token(expires_at=None, settings=test_settings)
            tokens.append(generated.value)

        # All tokens should have the same format characteristics
        for token in tokens:
            # No dots (no header)
            assert "." not in token
            # Last 3 characters should be numeric (length prefix)
            length_prefix = token[-3:]
            assert length_prefix.isnumeric()
            # Token should be longer than just the length prefix
            assert len(token) > 3

    def test_token_uniqueness(self, test_settings: AppSettings) -> None:
        """Test that generated tokens are unique."""
        tokens = set()

        for _ in range(10):
            generated = make_api_token(expires_at=None, settings=test_settings)
            tokens.add(generated.value)

        # All tokens should be unique
        assert len(tokens) == 10

    def test_token_expiration_handling(self, test_settings: AppSettings) -> None:
        """Test token expiration handling."""
        # Generate token with past expiration
        past_time = datetime.datetime.now() - datetime.timedelta(hours=1)
        generated = make_api_token(expires_at=past_time, settings=test_settings)

        # Should raise exception when decoding expired token
        with pytest.raises(Exception):  # HTTPException
            decode_api_token(generated.value, test_settings)

    @pytest.mark.asyncio
    async def test_auth_dependency_integration(
        self,
        test_settings: AppSettings,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test authentication dependency with real token."""
        from src.modules.auth.dependencies import verify_api_token

        # Generate valid token
        generated = make_api_token(expires_at=None, settings=test_settings)
        auth_token = f"Bearer {generated.value}"

        # Mock request
        request = MagicMock()
        request.method = "GET"

        # Verify token
        result = await verify_api_token(request, test_settings, auth_token=auth_token)

        assert result == auth_token

    def test_token_with_different_expiration_times(self, test_settings: AppSettings) -> None:
        """Test tokens with different expiration times."""
        # Token with 1 hour expiration
        exp_1h = datetime.datetime.now() + datetime.timedelta(hours=1)
        token_1h = make_api_token(expires_at=exp_1h, settings=test_settings)

        # Token with 1 day expiration
        exp_1d = datetime.datetime.now() + datetime.timedelta(days=1)
        token_1d = make_api_token(expires_at=exp_1d, settings=test_settings)

        # Token with max expiration
        token_max = make_api_token(expires_at=datetime.datetime.max, settings=test_settings)

        # All tokens should be decodable
        decoded_1h = decode_api_token(token_1h.value, test_settings)
        decoded_1d = decode_api_token(token_1d.value, test_settings)
        decoded_max = decode_api_token(token_max.value, test_settings)

        assert decoded_1h.exp == exp_1h
        assert decoded_1d.exp == exp_1d
        assert decoded_max.exp == datetime.datetime.max

    def test_token_identifier_format(self, test_settings: AppSettings) -> None:
        """Test that token identifier has expected format."""
        generated = make_api_token(expires_at=None, settings=test_settings)
        decoded = decode_api_token(generated.value, test_settings)

        # Token identifier should be alphanumeric and have expected length
        token_id = decoded.sub
        assert token_id.isalnum()
        assert len(token_id) >= 9  # 3 digits + 6 hex chars

    def test_token_hash_consistency(self, test_settings: AppSettings) -> None:
        """Test that token hashing is consistent."""
        generated = make_api_token(expires_at=None, settings=test_settings)
        decoded = decode_api_token(generated.value, test_settings)

        # Hash the token identifier multiple times
        hash1 = hash_token(decoded.sub)
        hash2 = hash_token(decoded.sub)
        hash3 = hash_token(decoded.sub)

        # All hashes should be identical
        assert hash1 == hash2 == hash3 == generated.hashed_value

    def test_token_with_special_characters_in_settings(self, test_settings: AppSettings) -> None:
        """Test token generation with special characters in secret key."""
        # Create settings with special characters in secret key
        special_settings = AppSettings(
            api_token=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr("test-secret-key-with-special-chars!@#$%^&*()"),
            jwt_algorithm="HS256",
        )

        generated = make_api_token(expires_at=None, settings=special_settings)
        decoded = decode_api_token(generated.value, special_settings)

        assert decoded.sub is not None
        assert decoded.exp is not None

    def test_token_with_different_algorithms(self, test_settings: AppSettings) -> None:
        """Test token generation with different JWT algorithms."""
        # Test with HS256
        hs256_settings = AppSettings(
            api_token=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr("test-secret-key"),
            jwt_algorithm="HS256",
        )

        token_hs256 = make_api_token(expires_at=None, settings=hs256_settings)
        decoded_hs256 = decode_api_token(token_hs256.value, hs256_settings)

        assert decoded_hs256.sub is not None

        # Test with HS512
        hs512_settings = AppSettings(
            api_token=SecretStr("test-token"),
            admin_username="test-username",
            admin_password=SecretStr("test-password"),
            secret_key=SecretStr("test-secret-key"),
            jwt_algorithm="HS512",
        )

        token_hs512 = make_api_token(expires_at=None, settings=hs512_settings)
        decoded_hs512 = decode_api_token(token_hs512.value, hs512_settings)

        assert decoded_hs512.sub is not None

    def test_token_edge_cases(self, test_settings: AppSettings) -> None:
        """Test token generation and decoding with edge cases."""
        # Test with very short expiration
        short_exp = datetime.datetime.now() + datetime.timedelta(seconds=1)
        token_short = make_api_token(expires_at=short_exp, settings=test_settings)

        # Should be decodable immediately
        decoded_short = decode_api_token(token_short.value, test_settings)
        assert decoded_short.exp == short_exp

        # Test with very long expiration
        long_exp = datetime.datetime.now() + datetime.timedelta(days=365)
        token_long = make_api_token(expires_at=long_exp, settings=test_settings)

        decoded_long = decode_api_token(token_long.value, test_settings)
        assert decoded_long.exp == long_exp

    @pytest.mark.asyncio
    async def test_auth_dependency_error_handling(self, test_settings: AppSettings) -> None:
        """Test error handling in authentication dependency."""
        from src.modules.auth.dependencies import verify_api_token

        request = MagicMock()
        request.method = "GET"

        # Test with malformed token
        with pytest.raises(Exception):  # HTTPException
            await verify_api_token(request, test_settings, auth_token="malformed-token")

        # Test with expired token
        past_time = datetime.datetime.now() - datetime.timedelta(hours=1)
        expired_token = make_api_token(expires_at=past_time, settings=test_settings)

        with pytest.raises(Exception):  # HTTPException
            await verify_api_token(
                request, test_settings, auth_token=f"Bearer {expired_token.value}"
            )

    def test_token_serialization_consistency(self, test_settings: AppSettings) -> None:
        """Test that token serialization is consistent."""
        # Generate multiple tokens and verify they can all be decoded
        tokens = []

        for _ in range(5):
            generated = make_api_token(expires_at=None, settings=test_settings)
            tokens.append(generated.value)

        # All tokens should be decodable
        for token in tokens:
            decoded = decode_api_token(token, test_settings)
            assert decoded.sub is not None
            assert decoded.exp is not None

    def test_token_with_none_expiration(self, test_settings: AppSettings) -> None:
        """Test token generation with None expiration (should use max datetime)."""
        token = make_api_token(expires_at=None, settings=test_settings)
        decoded = decode_api_token(token.value, test_settings)

        assert decoded.exp is not None
        assert decoded.exp == datetime.datetime.max
