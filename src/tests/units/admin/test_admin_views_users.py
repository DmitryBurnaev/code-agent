from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.modules.admin.views.users import UserAdminView, UserAdminForm
from src.db.models import User
from src.tests.mocks import MockUser


@pytest.fixture
def mock_user_make_password() -> Generator[MagicMock, Any, None]:
    with patch.object(User, "make_password", return_value="hashed-password") as mock_make_password:
        yield mock_make_password


class TestUserAdminForm:

    def test_form_creation(self) -> None:
        form = UserAdminForm()

        # Verify all fields exist
        assert hasattr(form, "username")
        assert hasattr(form, "email")
        assert hasattr(form, "new_password")
        assert hasattr(form, "repeat_password")
        assert hasattr(form, "is_admin")
        assert hasattr(form, "is_active")

    def test_validate_success_no_password(self) -> None:
        form = UserAdminForm()
        # Set form data using process method
        form.process(
            username="testuser",
            email="test@example.com",
            new_password="",
            repeat_password="",
            is_admin=False,
            is_active=True,
        )

        result = form.validate()
        assert result is True

    def test_validate_success_with_password(self) -> None:
        form = UserAdminForm()
        form.process(
            username="testuser",
            email="test@example.com",
            new_password="password123",
            repeat_password="password123",
            is_admin=False,
            is_active=True,
        )

        result = form.validate()
        assert result is True

    def test_validate_password_mismatch(self) -> None:
        form = UserAdminForm()
        form.process(
            username="testuser",
            email="test@example.com",
            new_password="password123",
            repeat_password="different123",
            is_admin=False,
            is_active=True,
        )

        result = form.validate()
        assert result is False
        assert form.new_password.errors == ("Passwords must be the same",)
        assert form.repeat_password.errors == ("Passwords must be the same",)

    def test_validate_with_extra_validators(self) -> None:
        form = UserAdminForm()
        form.process(
            username="testuser",
            email="test@example.com",
            new_password="password123",
            repeat_password="password123",
            is_admin=False,
            is_active=True,
        )

        extra_validators = {"username": [lambda form, field: True]}
        result = form.validate(extra_validators=extra_validators)
        assert result is True


class TestUserAdminView:

    @pytest.fixture
    def mock_app(self) -> MagicMock:
        app = MagicMock()
        return app

    @pytest.fixture
    def user_admin_view(self, mock_app: MagicMock) -> UserAdminView:
        view = UserAdminView()
        view.app = mock_app
        return view

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        request = MagicMock(spec=Request)
        return request

    @pytest.fixture
    def mock_user(self) -> MockUser:
        return MockUser(id=1, username="test-user", is_active=True)

    @pytest.fixture
    def mock_user_repository(self) -> Generator[AsyncMock, Any, None]:
        with patch("src.modules.admin.views.users.UserRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo_class.return_value = mock_repo
            yield mock_repo

    @pytest.fixture
    def mock_uow(self) -> Generator[AsyncMock, Any, None]:
        with patch("src.modules.admin.views.users.SASessionUOW") as mock_uow_class:
            mock_uow = AsyncMock()
            mock_uow_class.return_value.__aenter__.return_value = mock_uow
            mock_uow_class.return_value.__aexit__.return_value = None
            yield mock_uow


class TestUserAdminViewInsertModel(TestUserAdminView):

    @pytest.mark.asyncio
    async def test_insert_model_success(
        self,
        user_admin_view: UserAdminView,
        mock_request: MagicMock,
        mock_user: MockUser,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
        mock_user_make_password: MagicMock,
        mock_super_model_view_insert: MagicMock,
    ) -> None:
        mock_super_model_view_insert.return_value = mock_user
        mock_user_repository.get_by_username.return_value = None

        result = await user_admin_view.insert_model(
            mock_request,
            data={
                "username": "newuser",
                "email": "newuser@example.com",
                "new_password": "password123",
                "is_admin": False,
                "is_active": True,
            },
        )

        assert result == mock_user
        mock_super_model_view_insert.assert_called_once_with()
        # Check that password was hashed
        # call_args = mock_super_insert.call_args[0]
        # assert call_args[1]["password"] == "hashed-password"
        # assert "new_password" not in call_args[1]

    @pytest.mark.asyncio
    async def test_insert_model_no_password(
        self,
        user_admin_view: UserAdminView,
        mock_request: MagicMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        form_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "is_admin": False,
            "is_active": True,
        }

        # Execute and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await user_admin_view.insert_model(mock_request, form_data)

        # Verify
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Password required"

    @pytest.mark.asyncio
    async def test_insert_model_username_taken(
        self,
        user_admin_view: UserAdminView,
        mock_request: MagicMock,
        mock_user: MockUser,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        form_data = {
            "username": "existinguser",
            "email": "newuser@example.com",
            "new_password": "password123",
            "is_admin": False,
            "is_active": True,
        }
        mock_user_repository.get_by_username.return_value = mock_user

        # Execute and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await user_admin_view.insert_model(mock_request, form_data)

        # Verify
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Username already taken"

    @pytest.mark.asyncio
    async def test_insert_model_database_error(
        self,
        user_admin_view: UserAdminView,
        mock_request: MagicMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        form_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "new_password": "password123",
            "is_admin": False,
            "is_active": True,
        }
        mock_user_repository.get_by_username.side_effect = Exception("Database error")

        # Execute and expect exception
        with pytest.raises(Exception, match="Database error"):
            await user_admin_view.insert_model(mock_request, form_data)


class TestUserAdminViewUpdateModel(TestUserAdminView):

    @pytest.mark.asyncio
    async def test_update_model_success_with_password(
        self,
        user_admin_view: UserAdminView,
        mock_request: MagicMock,
        mock_user: MockUser,
        mock_user_make_password: MagicMock,
    ) -> None:
        # Setup mocks
        form_data = {
            "username": "updateduser",  # Should be removed
            "email": "updated@example.com",
            "new_password": "newpassword123",
            "repeat_password": "newpassword123",
            "is_admin": True,
            "is_active": True,
        }
        mock_super_update = AsyncMock(return_value=mock_user)
        user_admin_view.__class__.__bases__[0].update_model = mock_super_update

        # Execute
        result = await user_admin_view.update_model(mock_request, "1", form_data)

        # Verify
        assert result == mock_user
        mock_super_update.assert_called_once()
        # Check that username was removed and password was hashed
        call_args = mock_super_update.call_args[0]
        assert call_args[2]["password"] == "hashed-password"
        assert "username" not in call_args[2]
        assert "new_password" not in call_args[2]
        assert "repeat_password" not in call_args[2]

    @pytest.mark.asyncio
    async def test_update_model_success_without_password(
        self,
        user_admin_view: UserAdminView,
        mock_request: MagicMock,
        mock_user: MockUser,
    ) -> None:
        # Setup mocks
        form_data = {
            "username": "updateduser",  # Should be removed
            "email": "updated@example.com",
            "is_admin": True,
            "is_active": True,
        }
        mock_super_update = AsyncMock(return_value=mock_user)
        user_admin_view.__class__.__bases__[0].update_model = mock_super_update

        # Execute
        result = await user_admin_view.update_model(mock_request, "1", form_data)

        # Verify
        assert result == mock_user
        mock_super_update.assert_called_once()
        # Check that username was removed and password was not changed
        call_args = mock_super_update.call_args[0]
        assert "password" not in call_args[2]
        assert "username" not in call_args[2]
        assert "new_password" not in call_args[2]
        assert "repeat_password" not in call_args[2]

    @pytest.mark.asyncio
    async def test_update_model_database_error(
        self,
        user_admin_view: UserAdminView,
        mock_request: MagicMock,
        mock_user: MockUser,
    ) -> None:
        # Setup mocks
        form_data = {
            "email": "updated@example.com",
            "is_admin": True,
            "is_active": True,
        }
        mock_super_update = AsyncMock(side_effect=Exception("Database error"))
        user_admin_view.__class__.__bases__[0].update_model = mock_super_update

        # Execute and expect exception
        with pytest.raises(Exception, match="Database error"):
            await user_admin_view.update_model(mock_request, "1", form_data)


class TestUserAdminViewValidateUsername(TestUserAdminView):

    @pytest.mark.asyncio
    async def test_validate_username_success(
        self,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        mock_user_repository.get_by_username.return_value = None

        # Execute
        await UserAdminView._validate_username("newusername")

        # Verify
        mock_user_repository.get_by_username.assert_called_once_with("newusername")

    @pytest.mark.asyncio
    async def test_validate_username_taken(
        self,
        mock_user: MockUser,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        mock_user_repository.get_by_username.return_value = mock_user

        # Execute and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await UserAdminView._validate_username("existingusername")

        # Verify
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Username already taken"

    @pytest.mark.asyncio
    async def test_validate_username_database_error(
        self,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        mock_user_repository.get_by_username.side_effect = Exception("Database error")

        # Execute and expect exception
        with pytest.raises(Exception, match="Database error"):
            await UserAdminView._validate_username("testusername")


class TestUserAdminViewEdgeCases(TestUserAdminView):

    def test_form_field_attributes(self) -> None:
        form = UserAdminForm()

        # Test username field
        assert form.username.label.text == "Username"
        assert form.username.render_kw.get("required") is True

        # Test email field
        assert form.email.label.text == "Email"
        assert form.email.render_kw.get("required") is True

        # Test password fields
        assert form.new_password.label.text == "New Password"
        assert form.repeat_password.label.text == "Repeat New Password"

        # Test boolean fields
        assert form.is_admin.label.text == "Is Admin"
        assert form.is_active.label.text == "Is Active"

    @pytest.mark.asyncio
    async def test_insert_model_empty_password(
        self,
        user_admin_view: UserAdminView,
        mock_request: MagicMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        form_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "new_password": "",
            "is_admin": False,
            "is_active": True,
        }

        # Execute and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await user_admin_view.insert_model(mock_request, form_data)

        # Verify
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Password required"

    @pytest.mark.asyncio
    async def test_insert_model_none_password(
        self,
        user_admin_view: UserAdminView,
        mock_request: MagicMock,
        mock_user_repository: AsyncMock,
        mock_uow: AsyncMock,
    ) -> None:
        # Setup mocks
        form_data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "new_password": None,
            "is_admin": False,
            "is_active": True,
        }

        # Execute and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await user_admin_view.insert_model(mock_request, form_data)

        # Verify
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Password required"

    def test_form_validation_with_none_values(self) -> None:
        form = UserAdminForm()
        form.process(
            username="testuser",
            email="test@example.com",
            new_password=None,
            repeat_password=None,
            is_admin=False,
            is_active=True,
        )

        result = form.validate()
        assert result is True

    def test_form_validation_with_empty_strings(self) -> None:
        form = UserAdminForm()
        form.process(
            username="testuser",
            email="test@example.com",
            new_password="",
            repeat_password="",
            is_admin=False,
            is_active=True,
        )

        result = form.validate()
        assert result is True
