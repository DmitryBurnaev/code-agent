from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.web.auth import (
    SESSION_USER_ID,
    authenticate_web_user,
    get_current_web_user,
    login_web_user,
    logout_web_user,
)
from src.tests.mocks import MockUser


@pytest.fixture
def active_user() -> MockUser:
    user = MockUser(id=7, is_active=True, username="agent")
    user.verify_password = MagicMock(return_value=True)
    return user


@pytest.fixture
def mock_uow() -> MagicMock:
    with patch("src.modules.web.auth.SASessionUOW") as mock_uow_class:
        mock_uow = MagicMock()
        mock_uow_class.return_value.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow_class.return_value.__aexit__ = AsyncMock(return_value=None)
        yield mock_uow


@pytest.fixture
def mock_user_repository() -> MagicMock:
    with patch("src.modules.web.auth.UserRepository") as mock_repository_class:
        repository = MagicMock()
        repository.first = AsyncMock()
        repository.get_by_username = AsyncMock()
        mock_repository_class.return_value = repository
        yield repository


@pytest.mark.asyncio
async def test_get_current_web_user_returns_active_user(
    active_user: MockUser,
    mock_uow: MagicMock,
    mock_user_repository: MagicMock,
) -> None:
    request = SimpleNamespace(session={SESSION_USER_ID: active_user.id})
    mock_user_repository.first.return_value = active_user

    result = await get_current_web_user(request)

    assert result is active_user
    mock_user_repository.first.assert_awaited_once_with(instance_id=active_user.id)
    assert mock_uow.session is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [None, MockUser(id=7, is_active=False)])
async def test_get_current_web_user_clears_invalid_session(
    user: MockUser | None,
    mock_user_repository: MagicMock,
    mock_uow: MagicMock,
) -> None:
    request = SimpleNamespace(session={SESSION_USER_ID: 7})
    mock_user_repository.first.return_value = user

    result = await get_current_web_user(request)

    assert result is None
    assert request.session == {}
    assert mock_uow.session is not None


@pytest.mark.asyncio
async def test_get_current_web_user_ignores_malformed_session() -> None:
    request = SimpleNamespace(session={SESSION_USER_ID: "7"})

    assert await get_current_web_user(request) is None
    assert request.session == {SESSION_USER_ID: "7"}


@pytest.mark.asyncio
async def test_authenticate_web_user_accepts_active_user(
    active_user: MockUser,
    mock_uow: MagicMock,
    mock_user_repository: MagicMock,
) -> None:
    mock_user_repository.get_by_username.return_value = active_user

    result = await authenticate_web_user(username="agent", password="secret")

    assert result is active_user
    active_user.verify_password.assert_called_once_with("secret")
    mock_user_repository.get_by_username.assert_awaited_once_with(username="agent")
    assert mock_uow.session is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user", "password_ok"),
    [
        (None, False),
        (MockUser(id=7, is_active=False), True),
        (MockUser(id=7, is_active=True), False),
    ],
)
async def test_authenticate_web_user_rejects_invalid_user(
    user: MockUser | None,
    password_ok: bool,
    mock_user_repository: MagicMock,
    mock_uow: MagicMock,
) -> None:
    if user is not None:
        user.verify_password = MagicMock(return_value=password_ok)
    mock_user_repository.get_by_username.return_value = user

    result = await authenticate_web_user(username="agent", password="wrong")

    assert result is None
    assert mock_uow.session is not None


def test_login_and_logout_only_manage_web_user_session(active_user: MockUser) -> None:
    request = SimpleNamespace(session={"old": "value"})

    login_web_user(request, active_user)
    assert request.session == {SESSION_USER_ID: active_user.id}

    logout_web_user(request)
    assert request.session == {}
