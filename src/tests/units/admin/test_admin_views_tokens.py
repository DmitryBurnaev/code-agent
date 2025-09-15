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


class TestTokenAdminView:

    @pytest.fixture
    def mock_app(self) -> MagicMock:
        app = MagicMock()
        app.settings = MagicMock()
        app.settings.jwt_algorithm = "HS256"
        app.settings.app_secret_key = MagicMock()
        app.settings.app_secret_key.get_secret_value.return_value = "test-secret"
        return app

    @pytest.fixture
    def token_admin_view(self, mock_app: MagicMock) -> TokenAdminView:
        view = TokenAdminView()
        view.app = mock_app
        return view

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        request = MagicMock(spec=Request)
        request.query_params = {"pks": "1,2,3"}
        request.url_for = MagicMock()
        request.url_for.return_value = "/admin/tokens/list"
        return request

    @pytest.fixture
    def mock_user(self) -> MockUser:
        return MockUser(id=1, username="test-user", is_active=True)

    @pytest.fixture
    def mock_token(self, mock_user: MockUser) -> MagicMock:
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
    def mock_form_data(self) -> dict[str, Any]:
        return {
            "user": 1,
            "name": "test-token",
            "expires_at": datetime.datetime.now() + datetime.timedelta(days=30),
        }

    @pytest.fixture
    def mock_token_repository(self) -> Generator[AsyncMock, Any, None]:
        with patch("src.modules.admin.views.tokens.TokenRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            yield mock_repo

    @pytest.fixture
    def mock_uow(self) -> Generator[AsyncMock, Any, None]:
        with patch("src.modules.admin.views.tokens.SASessionUOW") as mock_uow_class:
            mock_uow = AsyncMock()
            mock_uow_class.return_value.__aenter__.return_value = mock_uow
            mock_uow_class.return_value.__aexit__.return_value = None
            yield mock_uow

    @pytest.fixture
    def mock_cache(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.views.tokens.InMemoryCache") as mock_cache_class:
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache
            yield mock_cache


class TestTokenAdminViewInsertModel(TestTokenAdminView):

    @pytest.fixture
    def mock_make_api_token(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.views.tokens.make_api_token") as mock_make_token:
            mock_token_info = MagicMock()
            mock_token_info.hashed_value = "hashed-token-value"
            mock_token_info.value = "raw-token-value"
            mock_make_token.return_value = mock_token_info
            yield mock_make_token

    @pytest.mark.asyncio
    async def test_insert_model_success(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_form_data: dict[str, Any],
        mock_token: Token,
        mock_cache: MagicMock,
        mock_make_api_token: MagicMock,
    ) -> None:
        # Setup mocks
        mock_super_insert = AsyncMock(return_value=mock_token)
        token_admin_view.__class__.__bases__[0].insert_model = mock_super_insert

        # Execute
        result = await token_admin_view.insert_model(mock_request, mock_form_data)

        # Verify
        assert result == mock_token
        mock_super_insert.assert_called_once()
        mock_cache.set.assert_called_once_with(f"token__{mock_token.id}", "raw-token-value", ttl=10)

    @pytest.mark.asyncio
    async def test_insert_model_without_expiration(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
        mock_cache: MagicMock,
        mock_make_api_token: MagicMock,
    ) -> None:
        # Setup mocks
        form_data = {"user": 1, "name": "test-token"}
        mock_super_insert = AsyncMock(return_value=mock_token)
        token_admin_view.__class__.__bases__[0].insert_model = mock_super_insert

        # Execute
        result = await token_admin_view.insert_model(mock_request, form_data)

        # Verify
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
    ) -> None:
        # Setup mocks
        expires_at = datetime.datetime.now() + datetime.timedelta(days=30)
        form_data = {"user": 1, "name": "test-token", "expires_at": expires_at}
        mock_super_insert = AsyncMock(return_value=mock_token)
        token_admin_view.__class__.__bases__[0].insert_model = mock_super_insert

        # Execute
        result = await token_admin_view.insert_model(mock_request, form_data)

        # Verify
        assert result == mock_token
        mock_make_api_token.assert_called_once_with(
            expires_at=expires_at, settings=token_admin_view.app.settings
        )


class TestTokenAdminViewGetObjectForDetails(TestTokenAdminView):

    @pytest.mark.asyncio
    async def test_get_object_for_details_success(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
        mock_cache: MagicMock,
    ) -> None:
        # Setup mocks
        mock_super_get = AsyncMock(return_value=mock_token)
        token_admin_view.__class__.__bases__[0].get_object_for_details = mock_super_get
        mock_cache.get.return_value = "raw-token-value"

        # Execute
        result = await token_admin_view.get_object_for_details(1)

        # Verify
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
    ) -> None:
        # Setup mocks
        mock_super_get = AsyncMock(return_value=mock_token)
        token_admin_view.__class__.__bases__[0].get_object_for_details = mock_super_get
        mock_cache.get.return_value = None

        # Execute
        result = await token_admin_view.get_object_for_details(1)

        # Verify
        assert result == mock_token
        assert result.raw_token == "None"
        mock_cache.get.assert_called_once_with(f"token__{mock_token.id}")
        mock_cache.invalidate.assert_called_once_with(f"token__{mock_token.id}")


class TestTokenAdminViewGetSaveRedirectUrl(TestTokenAdminView):

    def test_get_save_redirect_url(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
    ) -> None:
        # Setup mocks
        mock_build_url = MagicMock(return_value=URL("/admin/tokens/details/1"))
        token_admin_view._build_url_for = mock_build_url

        # Execute
        result = token_admin_view.get_save_redirect_url(mock_request, mock_token)

        # Verify
        assert result == URL("/admin/tokens/details/1")
        mock_build_url.assert_called_once_with(
            "admin:details", request=mock_request, obj=mock_token
        )


class TestTokenAdminViewActions(TestTokenAdminView):

    @pytest.mark.asyncio
    async def test_deactivate_tokens_success(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        mock_set_active = AsyncMock(return_value=RedirectResponse("/admin/tokens/list"))
        token_admin_view._set_active = mock_set_active

        # Execute
        result = await token_admin_view.deactivate_tokens(mock_request)

        # Verify
        assert isinstance(result, RedirectResponse)
        mock_set_active.assert_called_once_with(mock_request, is_active=False)

    @pytest.mark.asyncio
    async def test_activate_tokens_success(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        mock_set_active = AsyncMock(return_value=RedirectResponse("/admin/tokens/list"))
        token_admin_view._set_active = mock_set_active

        # Execute
        result = await token_admin_view.activate_tokens(mock_request)

        # Verify
        assert isinstance(result, RedirectResponse)
        mock_set_active.assert_called_once_with(mock_request, is_active=True)


class TestTokenAdminViewSetActive(TestTokenAdminView):

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


class TestTokenAdminViewEdgeCases(TestTokenAdminView):

    @pytest.mark.asyncio
    async def test_insert_model_database_error(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_form_data: dict[str, Any],
        mock_cache: MagicMock,
        mock_make_api_token: MagicMock,
    ) -> None:
        # Setup mocks
        mock_super_insert = AsyncMock(side_effect=Exception("Database error"))
        token_admin_view.__class__.__bases__[0].insert_model = mock_super_insert

        # Execute and expect exception
        with pytest.raises(Exception, match="Database error"):
            await token_admin_view.insert_model(mock_request, mock_form_data)

    @pytest.mark.asyncio
    async def test_get_object_for_details_database_error(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        # Setup mocks
        mock_super_get = AsyncMock(side_effect=Exception("Database error"))
        token_admin_view.__class__.__bases__[0].get_object_for_details = mock_super_get

        # Execute and expect exception
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
        # Setup mocks
        mock_uow.session = MagicMock()
        mock_token_repository.set_active.side_effect = Exception("Database error")

        # Execute and expect exception
        with pytest.raises(Exception, match="Database error"):
            await token_admin_view._set_active(mock_request, is_active=True)

    def test_get_save_redirect_url_error(
        self,
        token_admin_view: TokenAdminView,
        mock_request: MagicMock,
        mock_token: Token,
    ) -> None:
        # Setup mocks
        mock_build_url = MagicMock(side_effect=Exception("URL build error"))
        token_admin_view._build_url_for = mock_build_url

        # Execute and expect exception
        with pytest.raises(Exception, match="URL build error"):
            token_admin_view.get_save_redirect_url(mock_request, mock_token)
