"""Tests for authentication dependencies module."""

from datetime import timedelta

import pytest
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock

from starlette.exceptions import HTTPException

from src.modules.auth.dependencies import verify_api_token
from src.modules.auth.tokens import make_api_token
from src.settings import AppSettings
from src.tests.units.auth.conftest import GenMockPair, MockToken
from src.utils import utcnow


class TestVerifyAPIToken:
    """Tests for verify_api_token dependency."""

    @pytest.mark.asyncio
    async def test_verify_api_token_dependency_import(self) -> None:
        """Test that verify_api_token is properly imported."""
        from src.modules.auth.dependencies import verify_api_token

        assert callable(verify_api_token)

    @pytest.mark.asyncio
    async def test_verify_api_token_options_method(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test that OPTIONS method skips verification."""
        mock_request.method = "OPTIONS"

        result = await verify_api_token(mock_request, app_settings_test, auth_token=None)

        assert result == ""

    @pytest.mark.asyncio
    async def test_verify_api_token_no_token(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification without token."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token=None)

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_empty_token(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification with empty token."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="")

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_whitespace_token(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        """Test verification with whitespace-only token."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="   ")

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_with_bearer_prefix(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_token_repository_active: GenMockPair,
    ) -> None:
        """Test verification with Bearer prefix in token."""
        # TODO: reuse making token logic in fixtures
        auth_token = make_api_token(
            expires_at=utcnow() + timedelta(minutes=10),
            settings=app_settings_test,
        )
        result = await verify_api_token(
            mock_request,
            app_settings_test,
            auth_token=f"Bearer {auth_token.value}",
        )

        assert result == auth_token.value

    @pytest.mark.asyncio
    async def test_verify_api_token_without_bearer_prefix(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_make_token: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_session_uow: Tuple[MagicMock, AsyncMock],
        mock_token_repository_active: Tuple[MagicMock, AsyncMock],
    ) -> None:
        """Test verification without Bearer prefix in token."""
        auth_token = "test-token-value"
        result = await verify_api_token(mock_request, app_settings_test, auth_token=auth_token)

        assert result == auth_token

    @pytest.mark.asyncio
    async def test_verify_api_token_inactive_token(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_token: MockToken,
    ) -> None:
        """Test verification with inactive token."""
        mock_token.is_active = False

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "inactive token" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_inactive_user(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_token: MockToken,
    ) -> None:
        """Test verification with inactive user."""
        mock_token.is_active = True
        mock_token.user.is_active = False
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "user is not active" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_unknown_token(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_unknown_token: AsyncMock,
    ) -> None:
        """Test verification with unknown token."""

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "unknown token" in str(exc_info.value.detail)
        mock_unknown_token.assert_awaited_with(mock_hash_token.return_value)

    @pytest.mark.asyncio
    async def test_verify_api_token_no_identity(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token_no_identity: MagicMock,
    ) -> None:
        """Test verification with token that has no identity."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "token has no identity" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_none_identity(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token_none_identity: MagicMock,
    ) -> None:
        """Test verification with token that has None identity."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "token has no identity" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_api_token_database_error(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_repository_db_error: AsyncMock,
    ) -> None:
        """Test verification when database operation fails."""
        with pytest.raises(Exception) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_api_token_decode_error(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token_error: MagicMock,
    ) -> None:
        """Test verification when token decoding fails."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)
