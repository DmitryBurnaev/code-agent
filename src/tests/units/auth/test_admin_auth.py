import datetime
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from src.modules.admin.auth import AdminAuth, UserPayload
from src.settings import AppSettings
from src.tests.mocks import MockUser


class TestAdminAuth:
    """Test cases for AdminAuth class."""

    @pytest.fixture
    def app_settings(self) -> AppSettings:
        """Create test app settings."""
        return AppSettings(
            app_secret_key="test-secret-key",
            admin_session_expiration_time=3600,
            jwt_algorithm="HS256",
        )

    @pytest.fixture
    def admin_auth(self, app_settings: AppSettings) -> AdminAuth:
        """Create AdminAuth instance for testing."""
        return AdminAuth(secret_key="test-secret-key", settings=app_settings)

    @pytest.fixture
    def mock_user_admin(self) -> MockUser:
        """Create mock admin user."""
        user = MockUser(
            id=1,
            username="admin",
            is_active=True,
        )
        user.is_admin = True
        user.email = "admin@test.com"
        user.verify_password = MagicMock(return_value=True)
        return user

    @pytest.fixture
    def mock_user_regular(self) -> MockUser:
        """Create mock regular user."""
        user = MockUser(
            id=2,
            username="user",
            is_active=True,
        )
        user.is_admin = False
        user.email = "user@test.com"
        user.verify_password = MagicMock(return_value=True)
        return user

    @pytest.fixture
    def mock_user_inactive(self) -> MockUser:
        """Create mock inactive user."""
        user = MockUser(
            id=3,
            username="inactive",
            is_active=False,
        )
        user.is_admin = True
        user.email = "inactive@test.com"
        user.verify_password = MagicMock(return_value=True)
        return user

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        """Create mock FastAPI request."""
        request = MagicMock(spec=Request)
        request.session = {}
        return request

    @pytest.fixture
    def mock_form_data(self) -> dict[str, str]:
        """Create mock form data for login."""
        return {
            "username": "admin",
            "password": "password123",
        }

    @pytest.fixture
    def mock_form_async(self) -> AsyncMock:
        """Create async mock for request.form()."""
        form_mock = AsyncMock()
        form_mock.return_value = {
            "username": "admin",
            "password": "password123",
        }
        return form_mock

    @pytest.fixture
    def mock_user_repository(self) -> Generator[AsyncMock, Any, None]:
        """Mock UserRepository for testing."""
        with patch("src.modules.admin.auth.UserRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            yield mock_repo

    @pytest.fixture
    def mock_uow(self) -> Generator[AsyncMock, Any, None]:
        """Mock SASessionUOW for testing."""
        with patch("src.modules.admin.auth.SASessionUOW") as mock_uow_class:
            mock_uow = AsyncMock()
            mock_uow_class.return_value.__aenter__.return_value = mock_uow
            mock_uow_class.return_value.__aexit__.return_value = None
            yield mock_uow


class TestAdminAuthLogin(TestAdminAuth):
    """Test cases for AdminAuth.login method."""

    @pytest.mark.asyncio
    async def test_login_success(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_form_async: AsyncMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
        mock_user_admin: MockUser,
    ) -> None:
        """Test successful login."""
        # Setup mocks
        mock_request.form = mock_form_async
        mock_user_repository.get_by_username.return_value = mock_user_admin
        mock_uow.session = MagicMock()
        mock_user_admin.verify_password.return_value = True

        # Execute
        result = await admin_auth.login(mock_request)

        # Verify
        assert result is True
        assert "token" in mock_request.session
        mock_user_repository.get_by_username.assert_called_once_with(username="admin")

    @pytest.mark.asyncio
    async def test_login_user_not_found(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_form_async: AsyncMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        """Test login with non-existent user."""
        # Setup mocks
        mock_request.form = mock_form_async
        mock_user_repository.get_by_username.return_value = None
        mock_uow.session = MagicMock()

        # Execute
        result = await admin_auth.login(mock_request)

        # Verify
        assert result is False
        assert "token" not in mock_request.session

    @pytest.mark.asyncio
    async def test_login_invalid_password(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_form_async: AsyncMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
        mock_user_admin: MockUser,
    ) -> None:
        """Test login with invalid password."""
        # Setup mocks
        mock_request.form = mock_form_async
        mock_user_repository.get_by_username.return_value = mock_user_admin
        mock_uow.session = MagicMock()
        # Mock verify_password to return False
        mock_user_admin.verify_password = MagicMock(return_value=False)

        # Execute
        result = await admin_auth.login(mock_request)

        # Verify
        assert result is False
        assert "token" not in mock_request.session

    @pytest.mark.asyncio
    async def test_login_user_inactive(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_form_async: AsyncMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
        mock_user_inactive: MockUser,
    ) -> None:
        """Test login with inactive user."""
        # Setup mocks
        mock_request.form = mock_form_async
        mock_user_repository.get_by_username.return_value = mock_user_inactive
        mock_uow.session = MagicMock()
        mock_user_inactive.verify_password.return_value = True

        # Execute
        result = await admin_auth.login(mock_request)

        # Verify
        assert result is False
        assert "token" not in mock_request.session

    @pytest.mark.asyncio
    async def test_login_user_not_admin(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_form_async: AsyncMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
        mock_user_regular: MockUser,
    ) -> None:
        """Test login with non-admin user."""
        # Setup mocks
        mock_request.form = mock_form_async
        mock_user_repository.get_by_username.return_value = mock_user_regular
        mock_uow.session = MagicMock()
        mock_user_regular.verify_password.return_value = True

        # Execute
        result = await admin_auth.login(mock_request)

        # Verify
        assert result is False
        assert "token" not in mock_request.session


class TestAdminAuthLogout(TestAdminAuth):
    """Test cases for AdminAuth.logout method."""

    @pytest.mark.asyncio
    async def test_logout_success(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
    ) -> None:
        """Test successful logout."""
        # Setup - add some session data
        mock_request.session = {"token": "some-token", "other": "data"}

        # Execute
        result = await admin_auth.logout(mock_request)

        # Verify
        assert result is True
        assert mock_request.session == {}

    @pytest.mark.asyncio
    async def test_logout_empty_session(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
    ) -> None:
        """Test logout with empty session."""
        # Setup - empty session
        mock_request.session = {}

        # Execute
        result = await admin_auth.logout(mock_request)

        # Verify
        assert result is True
        assert mock_request.session == {}


class TestAdminAuthAuthenticate(TestAdminAuth):
    """Test cases for AdminAuth.authenticate method."""

    @pytest.mark.asyncio
    async def test_authenticate_success(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
        mock_user_admin: MockUser,
    ) -> None:
        """Test successful authentication."""
        # Setup mocks
        mock_request.session = {"token": "valid-token"}
        mock_user_repository.first.return_value = mock_user_admin
        mock_uow.session = MagicMock()

        # Mock token decoding
        with patch.object(admin_auth, "_decode_token", return_value=1):
            # Execute
            result = await admin_auth.authenticate(mock_request)

        # Verify
        assert result is True
        mock_user_repository.first.assert_called_once_with(instance_id=1)

    @pytest.mark.asyncio
    async def test_authenticate_no_token(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
    ) -> None:
        """Test authentication with no token in session."""
        # Setup - no token in session
        mock_request.session = {}

        # Execute
        result = await admin_auth.authenticate(mock_request)

        # Verify
        assert result is False

    @pytest.mark.asyncio
    async def test_authenticate_invalid_token(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
    ) -> None:
        """Test authentication with invalid token."""
        # Setup
        mock_request.session = {"token": "invalid-token"}

        # Mock token decoding to return None
        with patch.object(admin_auth, "_decode_token", return_value=None):
            # Execute
            result = await admin_auth.authenticate(mock_request)

        # Verify
        assert result is False

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        """Test authentication with user not found."""
        # Setup mocks
        mock_request.session = {"token": "valid-token"}
        mock_user_repository.first.return_value = None
        mock_uow.session = MagicMock()

        # Mock token decoding
        with patch.object(admin_auth, "_decode_token", return_value=999):
            # Execute
            result = await admin_auth.authenticate(mock_request)

        # Verify
        assert result is False

    @pytest.mark.asyncio
    async def test_authenticate_user_inactive(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
        mock_user_inactive: MockUser,
    ) -> None:
        """Test authentication with inactive user."""
        # Setup mocks
        mock_request.session = {"token": "valid-token"}
        mock_user_repository.first.return_value = mock_user_inactive
        mock_uow.session = MagicMock()

        # Mock token decoding
        with patch.object(admin_auth, "_decode_token", return_value=3):
            # Execute
            result = await admin_auth.authenticate(mock_request)

        # Verify
        assert result is False

    @pytest.mark.asyncio
    async def test_authenticate_user_not_admin(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
        mock_user_regular: MockUser,
    ) -> None:
        """Test authentication with non-admin user."""
        # Setup mocks
        mock_request.session = {"token": "valid-token"}
        mock_user_repository.first.return_value = mock_user_regular
        mock_uow.session = MagicMock()

        # Mock token decoding
        with patch.object(admin_auth, "_decode_token", return_value=2):
            # Execute
            result = await admin_auth.authenticate(mock_request)

        # Verify
        assert result is False


class TestAdminAuthTokenHandling(TestAdminAuth):
    """Test cases for AdminAuth token handling methods."""

    def test_encode_token(
        self,
        admin_auth: AdminAuth,
        app_settings: AppSettings,
    ) -> None:
        """Test token encoding."""
        # Setup
        user_payload: UserPayload = {
            "id": 1,
            "username": "admin",
            "email": "admin@test.com",
        }

        # Execute
        token = admin_auth._encode_token(user_payload)

        # Verify
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT format

    def test_decode_token_success(
        self,
        admin_auth: AdminAuth,
        app_settings: AppSettings,
    ) -> None:
        """Test successful token decoding."""
        # Setup - create a valid token first
        user_payload: UserPayload = {
            "id": 1,
            "username": "admin",
            "email": "admin@test.com",
        }
        token = admin_auth._encode_token(user_payload)

        # Execute
        user_id = admin_auth._decode_token(token)

        # Verify
        assert user_id == 1

    def test_decode_token_invalid(
        self,
        admin_auth: AdminAuth,
    ) -> None:
        """Test token decoding with invalid token."""
        # Execute
        user_id = admin_auth._decode_token("invalid.token.here")

        # Verify
        assert user_id is None

    def test_decode_token_expired(
        self,
        admin_auth: AdminAuth,
        app_settings: AppSettings,
    ) -> None:
        """Test token decoding with expired token."""
        # Setup - create expired token
        user_payload: UserPayload = {
            "id": 1,
            "username": "admin",
            "email": "admin@test.com",
        }

        # Mock jwt_decode to raise PyJWTError for expired token
        with patch("src.modules.admin.auth.jwt_decode") as mock_decode:
            from jwt import PyJWTError

            mock_decode.side_effect = PyJWTError("Token expired")

            # Execute
            user_id = admin_auth._decode_token("expired.token.here")

        # Verify
        assert user_id is None


class TestAdminAuthCheckUser(TestAdminAuth):
    """Test cases for AdminAuth._check_user static method."""

    def test_check_user_success_with_password(
        self,
        mock_user_admin: MockUser,
    ) -> None:
        """Test successful user check with password verification."""
        # Setup
        mock_user_admin.verify_password.return_value = True

        # Execute
        ok, message = AdminAuth._check_user(
            mock_user_admin, identety="admin", password="password123"
        )

        # Verify
        assert ok is True
        assert message == "User is active"
        mock_user_admin.verify_password.assert_called_once_with("password123")

    def test_check_user_success_without_password(
        self,
        mock_user_admin: MockUser,
    ) -> None:
        """Test successful user check without password verification."""
        # Execute
        ok, message = AdminAuth._check_user(mock_user_admin, identety=1)

        # Verify
        assert ok is True
        assert message == "User is active"

    def test_check_user_not_found(
        self,
    ) -> None:
        """Test user check with None user."""
        # Execute
        ok, message = AdminAuth._check_user(None, identety="nonexistent")

        # Verify
        assert ok is False
        assert message == "User not found"

    def test_check_user_invalid_password(
        self,
        mock_user_admin: MockUser,
    ) -> None:
        """Test user check with invalid password."""
        # Setup
        mock_user_admin.verify_password.return_value = False

        # Execute
        ok, message = AdminAuth._check_user(
            mock_user_admin, identety="admin", password="wrongpassword"
        )

        # Verify
        assert ok is False
        assert message == "Invalid password"

    def test_check_user_inactive(
        self,
        mock_user_inactive: MockUser,
    ) -> None:
        """Test user check with inactive user."""
        # Execute
        ok, message = AdminAuth._check_user(mock_user_inactive, identety=3)

        # Verify
        assert ok is False
        assert message == "User inactive"

    def test_check_user_not_admin(
        self,
        mock_user_regular: MockUser,
    ) -> None:
        """Test user check with non-admin user."""
        # Execute
        ok, message = AdminAuth._check_user(mock_user_regular, identety=2)

        # Verify
        assert ok is False
        assert message == "User is not an admin"


class TestAdminAuthEdgeCases(TestAdminAuth):
    """Test cases for AdminAuth edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_login_database_error(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_form_async: AsyncMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        """Test login with database error."""
        # Setup mocks
        mock_request.form = mock_form_async
        mock_user_repository.get_by_username.side_effect = Exception("Database error")
        mock_uow.session = MagicMock()

        # Execute and expect exception to be raised
        with pytest.raises(Exception, match="Database error"):
            await admin_auth.login(mock_request)

    @pytest.mark.asyncio
    async def test_authenticate_database_error(
        self,
        admin_auth: AdminAuth,
        mock_request: MagicMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        """Test authentication with database error."""
        # Setup mocks
        mock_request.session = {"token": "valid-token"}
        mock_user_repository.first.side_effect = Exception("Database error")
        mock_uow.session = MagicMock()

        # Mock token decoding
        with patch.object(admin_auth, "_decode_token", return_value=1):
            # Execute and expect exception to be raised
            with pytest.raises(Exception, match="Database error"):
                await admin_auth.authenticate(mock_request)

    def test_encode_token_with_custom_expiration(
        self,
        admin_auth: AdminAuth,
        app_settings: AppSettings,
    ) -> None:
        """Test token encoding with custom expiration time."""
        # Setup
        user_payload: UserPayload = {
            "id": 1,
            "username": "admin",
            "email": "admin@test.com",
        }

        # Mock utcnow to return specific time
        with patch("src.modules.admin.auth.utcnow") as mock_utcnow:
            fixed_time = datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
            mock_utcnow.return_value = fixed_time

            # Execute
            token = admin_auth._encode_token(user_payload)

        # Verify
        assert isinstance(token, str)
        assert len(token.split(".")) == 3

    def test_check_user_with_string_identity(
        self,
        mock_user_admin: MockUser,
    ) -> None:
        """Test user check with string identity."""
        # Execute
        ok, message = AdminAuth._check_user(mock_user_admin, identety="admin")

        # Verify
        assert ok is True
        assert message == "User is active"

    def test_check_user_with_int_identity(
        self,
        mock_user_admin: MockUser,
    ) -> None:
        """Test user check with integer identity."""
        # Execute
        ok, message = AdminAuth._check_user(mock_user_admin, identety=1)

        # Verify
        assert ok is True
        assert message == "User is active"
