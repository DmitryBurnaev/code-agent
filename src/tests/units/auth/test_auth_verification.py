from datetime import timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock

from starlette.exceptions import HTTPException

from src.modules.auth.dependencies import verify_api_token
from src.modules.auth.tokens import make_api_token
from src.settings import AppSettings
from src.utils import utcnow
from src.tests.mocks import MockAPIToken


@pytest.mark.asyncio
class TestVerifyAPIToken:

    async def test_verify_api_token_dependency_import(self) -> None:
        from src.modules.auth.dependencies import verify_api_token

        assert callable(verify_api_token)

    async def test_verify_api_token_options_method(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        mock_request.method = "OPTIONS"

        result = await verify_api_token(mock_request, app_settings_test, auth_token=None)

        assert result == ""

    async def test_verify_api_token_no_token(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token=None)

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    async def test_verify_api_token_empty_token(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="")

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    async def test_verify_api_token_whitespace_token(
        self, app_settings_test: AppSettings, mock_request: MagicMock
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="   ")

        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)

    async def test_verify_api_token_with_bearer_prefix(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_db_api_token__active: MockAPIToken,
    ) -> None:
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

    async def test_verify_api_token_without_bearer_prefix(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_db_api_token__active: MockAPIToken,
    ) -> None:
        auth_token = "test-token-value"
        result = await verify_api_token(mock_request, app_settings_test, auth_token=auth_token)
        assert result == auth_token

    async def test_verify_api_token_inactive_token(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_api_token_inactive: MockAPIToken,
    ) -> None:
        mock_api_token_inactive.is_active = False

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "inactive token" in str(exc_info.value.detail)

    async def test_verify_api_token_inactive_user(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_api_token_inactive: MockAPIToken,
    ) -> None:
        mock_api_token_inactive.is_active = True
        mock_api_token_inactive.user.is_active = False
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "user is not active" in str(exc_info.value.detail)

    async def test_verify_api_token_unknown_token(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_api_token_unknown: AsyncMock,
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "unknown token" in str(exc_info.value.detail)
        mock_api_token_unknown.assert_awaited_with(mock_hash_token.return_value)

    async def test_verify_api_token_no_identity(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token_no_identity: MagicMock,
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "token has no identity" in str(exc_info.value.detail)

    async def test_verify_api_token_none_identity(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token_none_identity: MagicMock,
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "token has no identity" in str(exc_info.value.detail)

    async def test_verify_api_token_database_error(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token: MagicMock,
        mock_hash_token: MagicMock,
        mock_repository_db_error: AsyncMock,
    ) -> None:
        with pytest.raises(Exception) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert "Database error" in str(exc_info.value)

    async def test_verify_api_token_decode_error(
        self,
        app_settings_test: AppSettings,
        mock_request: MagicMock,
        mock_decode_token_error: MagicMock,
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_token(mock_request, app_settings_test, auth_token="test-token")

        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)
