import datetime
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import RedirectResponse

from src.modules.admin.views.tokens import TokenAdminView
from src.db.models import Token
from src.tests.mocks import MockUser


@pytest.fixture
def token_admin_view(test_app: MagicMock) -> TokenAdminView:
    view = TokenAdminView()
    view.app = test_app
    return view


@pytest.fixture
def mock_request() -> MagicMock:
    request = MagicMock(spec=Request)
    request.query_params = {"pks": "1,2,3"}
    request.url_for = MagicMock()
    request.url_for.return_value = "/admin/tokens/list"
    return request


@pytest.fixture
def mock_user() -> MockUser:
    return MockUser(id=1, username="test-user", is_active=True)


@pytest.fixture
def mock_token(mock_user: MockUser) -> MagicMock:
    token = MagicMock(spec=Token)
    token.id = 1
    token.user_id = 1
    token.user = mock_user
    token.name = "test-token"
    token.token = "hashed-token-value"
    token.is_active = True
    token.expires_at = datetime.datetime.now() + datetime.timedelta(days=30)
    token.created_at = datetime.datetime.now()
    return token


@pytest.fixture
def mock_form_data() -> dict[str, Any]:
    return {
        "user": 1,
        "name": "test-token",
        "expires_at": datetime.datetime.now() + datetime.timedelta(days=30),
    }


@pytest.fixture
def mock_token_repository() -> Generator[AsyncMock, Any, None]:
    with patch("src.modules.admin.views.tokens.TokenRepository") as mock_repo_class:
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        yield mock_repo


@pytest.fixture
def mock_uow() -> Generator[AsyncMock, Any, None]:
    with patch("src.modules.admin.views.tokens.SASessionUOW") as mock_uow_class:
        mock_uow = AsyncMock()
        mock_uow_class.return_value.__aenter__.return_value = mock_uow
        mock_uow_class.return_value.__aexit__.return_value = None
        yield mock_uow


@pytest.fixture
def mock_cache() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.admin.views.tokens.InMemoryCache") as mock_cache_class:
        mock_cache = MagicMock()
        mock_cache_class.return_value = mock_cache
        yield mock_cache


@pytest.fixture
def mock_make_api_token() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.admin.views.tokens.make_api_token") as mock_make_token:
        mock_token_info = MagicMock()
        mock_token_info.hashed_value = "hashed-token-value"
        mock_token_info.value = "raw-token-value"
        mock_make_token.return_value = mock_token_info
        yield mock_make_token


class TestTokenAdminViewInsertModel:

    @pytest.mark.asyncio
    async def test_insert_model_success(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_form_data: dict[str, Any],
        mock_token: Token,
        mock_cache: MagicMock,
        mock_make_api_token: MagicMock,
        mock_super_model_view_insert: MagicMock,
    ) -> None:
        mock_super_model_view_insert.return_value = mock_token
        result = await token_admin_view.insert_model(mock_request, mock_form_data)

        assert result == mock_token
        mock_super_model_view_insert.assert_called_once()
        mock_cache.set.assert_called_once_with(f"token__{mock_token.id}", "raw-token-value", ttl=10)

    @pytest.mark.asyncio
    async def test_insert_model_without_expiration(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
        mock_cache: MagicMock,
        mock_make_api_token: MagicMock,
        mock_super_model_view_insert: MagicMock,
    ) -> None:
        mock_super_model_view_insert.return_value = mock_token

        result = await token_admin_view.insert_model(
            mock_request,
            data={"user": 1, "name": "test-token"},
        )

        assert result == mock_token
        mock_make_api_token.assert_called_once_with(
            expires_at=None, settings=token_admin_view.app.settings
        )

    @pytest.mark.asyncio
    async def test_insert_model_with_expiration(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
        mock_cache: MagicMock,
        mock_make_api_token: MagicMock,
        mock_super_model_view_insert: MagicMock,
    ) -> None:
        mock_super_model_view_insert.return_value = mock_token
        expires_at = datetime.datetime.now() + datetime.timedelta(days=30)

        result = await token_admin_view.insert_model(
            mock_request,
            data={"user": 1, "name": "test-token", "expires_at": expires_at},
        )

        assert result == mock_token
        mock_make_api_token.assert_called_once_with(
            expires_at=expires_at, settings=token_admin_view.app.settings
        )


class TestTokenAdminViewOperations:

    @pytest.mark.asyncio
    async def test_get_object_for_details_success(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
        mock_cache: MagicMock,
        mock_super_model_view_get_details: MagicMock,
    ) -> None:
        # Setup mocks
        mock_super_model_view_get_details.return_value = mock_token
        mock_cache.get.return_value = "raw-token-value"

        result = await token_admin_view.get_object_for_details(value=mock_token.id)

        assert result == mock_token
        assert result.raw_token == "raw-token-value"
        mock_cache.get.assert_called_once_with(f"token__{mock_token.id}")
        mock_cache.invalidate.assert_called_once_with(f"token__{mock_token.id}")

    @pytest.mark.asyncio
    async def test_get_object_for_details_no_cache(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
        mock_cache: MagicMock,
        mock_super_model_view_get_details: MagicMock,
    ) -> None:
        mock_super_model_view_get_details.return_value = mock_token
        mock_cache.get.return_value = None

        result = await token_admin_view.get_object_for_details(1)

        assert result == mock_token
        assert result.raw_token == "None"
        mock_cache.get.assert_called_once_with(f"token__{mock_token.id}")
        mock_cache.invalidate.assert_called_once_with(f"token__{mock_token.id}")

    def test_get_save_redirect_url(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
        mock_super_model_url_build_for: MagicMock,
    ) -> None:
        mock_super_model_url_build_for.return_value = URL("/admin/tokens/details/1")

        result = token_admin_view.get_save_redirect_url(mock_request, mock_token)

        # Verify
        assert result == URL("/admin/tokens/details/1")
        mock_super_model_url_build_for.assert_called_once_with(
            "admin:details", request=mock_request, obj=mock_token
        )


@pytest.mark.asyncio
class TestTokenAdminViewActions:

    @pytest.fixture
    def mock_set_active(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.views.tokens.TokenAdminView._set_active") as mock_set_active:
            yield mock_set_active

    async def test_deactivate_tokens_success(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_set_active: MagicMock,
    ) -> None:
        mock_set_active.return_value = RedirectResponse("/admin/tokens/list")
        result = await token_admin_view.deactivate_tokens(mock_request)

        assert isinstance(result, RedirectResponse)
        mock_set_active.assert_called_once_with(mock_request, is_active=False)

    async def test_activate_tokens_success(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_set_active: MagicMock,
    ) -> None:
        mock_set_active.return_value = RedirectResponse("/admin/tokens/list")

        result = await token_admin_view.activate_tokens(mock_request)

        assert isinstance(result, RedirectResponse)
        mock_set_active.assert_called_once_with(mock_request, is_active=True)


class TestTokenAdminViewSetActive:

    @pytest.mark.asyncio
    async def test_set_active_success(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        mock_uow.session = MagicMock()
        mock_token_repository.set_active.return_value = None

        # Execute
        result = await token_admin_view._set_active(mock_request, is_active=True)

        # Verify
        assert isinstance(result, RedirectResponse)
        mock_token_repository.set_active.assert_called_once_with(["1", "2", "3"], is_active=True)
        mock_uow.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_active_no_pks(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        mock_request.query_params = {"pks": ""}
        mock_uow.session = MagicMock()
        mock_token_repository.set_active.return_value = None

        # Execute - should work with empty string
        result = await token_admin_view._set_active(mock_request, is_active=True)

        # Verify
        assert isinstance(result, RedirectResponse)
        mock_token_repository.set_active.assert_called_once_with([""], is_active=True)

    @pytest.mark.asyncio
    async def test_set_active_empty_pks(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        mock_request.query_params = {}
        mock_uow.session = MagicMock()
        mock_token_repository.set_active.return_value = None

        # Execute - should work with empty list
        result = await token_admin_view._set_active(mock_request, is_active=True)

        # Verify
        assert isinstance(result, RedirectResponse)
        mock_token_repository.set_active.assert_called_once_with([""], is_active=True)

    @pytest.mark.asyncio
    async def test_set_active_deactivate(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        mock_uow.session = MagicMock()
        mock_token_repository.set_active.return_value = None

        # Execute
        result = await token_admin_view._set_active(mock_request, is_active=False)

        # Verify
        assert isinstance(result, RedirectResponse)
        mock_token_repository.set_active.assert_called_once_with(["1", "2", "3"], is_active=False)
        mock_uow.commit.assert_called_once()


class TestTokenAdminViewEdgeCases:

    @pytest.mark.asyncio
    async def test_insert_model_database_error(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_form_data: dict[str, Any],
        mock_super_model_view_insert: MagicMock,
    ) -> None:
        mock_super_model_view_insert.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await token_admin_view.insert_model(mock_request, mock_form_data)

    @pytest.mark.asyncio
    async def test_get_object_for_details_database_error(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_cache: MagicMock,
        mock_super_model_view_get_details: MagicMock,
    ) -> None:
        mock_super_model_view_get_details.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await token_admin_view.get_object_for_details(1)

    @pytest.mark.asyncio
    async def test_set_active_database_error(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        mock_uow.session = MagicMock()
        mock_token_repository.set_active.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await token_admin_view._set_active(mock_request, is_active=True)

    def test_get_save_redirect_url_error(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
        mock_super_model_url_build_for: MagicMock,
    ) -> None:
        mock_super_model_url_build_for.side_effect = Exception("URL build error")

        with pytest.raises(Exception, match="URL build error"):
            token_admin_view.get_save_redirect_url(mock_request, mock_token)
