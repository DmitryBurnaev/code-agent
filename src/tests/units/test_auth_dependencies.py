"""Tests for authentication dependencies module."""

import pytest
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Depends, HTTPException

from src.modules.auth.dependencies import (
    verify_api_token,
    VerifyAPITokenDep,
)
from src.settings import AppSettings
from pydantic import SecretStr


# Module-level fixtures
@pytest.fixture
def test_settings() -> AppSettings:
    """Return test settings."""
    return AppSettings(
        api_token=SecretStr("test-token"),
        admin_username="test-username",
        admin_password=SecretStr("test-password"),
        secret_key=SecretStr("test-secret-key-for-dependencies"),
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


@pytest.fixture
def mock_token_repository_inactive_token() -> Tuple[MagicMock, AsyncMock]:
    """Mock TokenRepository with inactive token."""
    with patch("src.modules.auth.dependencies.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_token = MagicMock()
        mock_token.is_active = False
        mock_repo.get_by_token.return_value = mock_token
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_token_repository_inactive_user() -> Tuple[MagicMock, AsyncMock]:
    """Mock TokenRepository with inactive user."""
    with patch("src.modules.auth.dependencies.TokenRepository") as mock_repo_class:
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
    with patch("src.modules.auth.dependencies.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo.get_by_token.return_value = None
        mock_repo_class.return_value = mock_repo
        yield mock_repo_class, mock_repo


@pytest.fixture
def mock_decode_token_no_identity() -> MagicMock:
    """Mock decode_api_token function with no identity."""
    with patch("src.modules.auth.dependencies.decode_api_token") as mock:
        mock.return_value = MagicMock(sub="")
        yield mock


@pytest.fixture
def mock_decode_token_none_identity() -> MagicMock:
    """Mock decode_api_token function with None identity."""
    with patch("src.modules.auth.dependencies.decode_api_token") as mock:
        mock.return_value = MagicMock(sub=None)
        yield mock


@pytest.fixture
def mock_decode_token_error() -> MagicMock:
    """Mock decode_api_token function that raises error."""
    with patch("src.modules.auth.dependencies.decode_api_token") as mock:
        mock.side_effect = HTTPException(status_code=401, detail="Invalid token")
        yield mock


@pytest.fixture
def mock_session_uow_error() -> MagicMock:
    """Mock SASessionUOW context manager that raises error."""
    with patch("src.modules.auth.dependencies.SASessionUOW") as mock_uow:
        mock_uow.side_effect = Exception("Database error")
        yield mock_uow


class TestVerifyAPITokenDependency:
    """Tests for verify_api_token dependency."""

    @pytest.mark.asyncio
    async def test_verify_api_token_dependency_import(self) -> None:
        """Test that verify_api_token is properly imported."""
        from src.modules.auth.dependencies import verify_api_token

        assert callable(verify_api_token)

    @pytest.mark.asyncio
    async def test_verify_api_token_dependency_type(self) -> None:
        """Test that VerifyAPITokenDep is a FastAPI dependency."""
        assert isinstance(VerifyAPITokenDep, Depends)

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
    async def test_verify_api_token_empty_token(
        self, test_settings: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification with empty token."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="")

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_whitespace_token(
        self, test_settings: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification with whitespace-only token."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="   ")

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_with_bearer_prefix(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_make_token: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_active: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with Bearer prefix in token."""
        auth_token = "Bearer test-token-value"
        result = await verify_api_token(mock_request, test_settings, auth_token=auth_token)

        assert result == auth_token

    @pytest.mark.asyncio
    async def test_verify_api_token_without_bearer_prefix(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_make_token: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_active: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification without Bearer prefix in token."""
        auth_token = "test-token-value"
        result = await verify_api_token(mock_request, test_settings, auth_token=auth_token)

        assert result == auth_token

    @pytest.mark.asyncio
    async def test_verify_api_token_inactive_token(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_inactive_token: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with inactive token."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "inactive token" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_inactive_user(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_inactive_user: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with inactive user."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "user is not active" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_unknown_token(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_unknown_token: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification with unknown token."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "unknown token" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_no_identity(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_decode_token_no_identity: MagicMock,
    ) -> None:
        """Test verification with token that has no identity."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "token has no identity" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_none_identity(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_decode_token_none_identity: MagicMock,
    ) -> None:
        """Test verification with token that has None identity."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "token has no identity" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_database_error(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow_error: MagicMock,
    ) -> None:
        """Test verification when database operation fails."""
        with pytest.raises(Exception) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="test-token")

        assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_api_token_decode_error(
        self,
        test_settings: AppSettings,
        mock_request: MagicMock,
        mock_decode_token_error: MagicMock,
    ) -> None:
        """Test verification when token decoding fails."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, test_settings, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)


class TestDependenciesModule:
    """Tests for dependencies module structure."""

    def test_module_imports(self) -> None:
        """Test that all expected functions are imported."""
        from src.modules.auth.dependencies import verify_api_token, VerifyAPITokenDep

        assert callable(verify_api_token)
        assert isinstance(VerifyAPITokenDep, Depends)

    def test_all_exports(self) -> None:
        """Test that __all__ contains expected exports."""
        from src.modules.auth.dependencies import __all__

        expected_exports = ["verify_api_token"]
        assert __all__ == expected_exports
