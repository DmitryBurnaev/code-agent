from collections.abc import Generator
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

from src.db.models import User
from src.modules.web.auth import (
    SESSION_USER_ID,
    authenticate_web_user,
    get_current_web_user,
    login_web_user,
    logout_web_user,
)


@pytest.fixture
def active_user() -> User:
    return User(
        id=7,
        username="agent",
        password="hashed-password",
        email="agent@test.com",
        is_active=True,
        is_admin=False,
    )


@pytest.fixture
def mock_uow() -> Generator[MagicMock, None, None]:
    with patch("src.modules.web.auth.SASessionUOW") as mock_uow_class:
        mock_uow = MagicMock()
        mock_uow_class.return_value.__aenter__ = AsyncMock(return_value=mock_uow)
        mock_uow_class.return_value.__aexit__ = AsyncMock(return_value=None)
        yield mock_uow


@pytest.fixture
def mock_user_repository() -> Generator[MagicMock, None, None]:
    with patch("src.modules.web.auth.UserRepository") as mock_repository_class:
        repository = MagicMock()
        repository.first = AsyncMock()
        repository.get_by_username = AsyncMock()
        mock_repository_class.return_value = repository
        yield repository


def get_request(session: dict[str, int | str]) -> Request:
    # noinspection PyInvalidCast
    return cast(Request, SimpleNamespace(session=session))


@pytest.mark.asyncio
async def test_get_current_web_user_returns_active_user(
    active_user: User,
    mock_uow: MagicMock,
    mock_user_repository: MagicMock,
) -> None:
    request = get_request(session={SESSION_USER_ID: active_user.id})
    mock_user_repository.first.return_value = active_user

    result = await get_current_web_user(request)

    assert result is active_user
    mock_user_repository.first.assert_awaited_once_with(instance_id=active_user.id)
    assert mock_uow.session is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user",
    [
        None,
        User(
            id=7,
            username="inactive",
            password="hashed-password",
            email="inactive@test.com",
            is_active=False,
            is_admin=False,
        ),
    ],
)
async def test_get_current_web_user_clears_invalid_session(
    user: User | None,
    mock_user_repository: MagicMock,
    mock_uow: MagicMock,
) -> None:
    request = get_request(session={SESSION_USER_ID: 7})
    mock_user_repository.first.return_value = user

    result = await get_current_web_user(request)

    assert result is None
    assert request.session == {}
    assert mock_uow.session is not None


@pytest.mark.asyncio
async def test_get_current_web_user_ignores_malformed_session() -> None:
    request = get_request(session={SESSION_USER_ID: "7"})

    assert await get_current_web_user(request) is None
    assert request.session == {SESSION_USER_ID: "7"}


@pytest.mark.asyncio
async def test_authenticate_web_user_accepts_active_user(
    active_user: User,
    mock_uow: MagicMock,
    mock_user_repository: MagicMock,
) -> None:
    mock_user_repository.get_by_username.return_value = active_user

    with patch.object(User, "verify_password", return_value=True) as verify_password:
        result = await authenticate_web_user(username="agent", password="secret")

    assert result is active_user
    verify_password.assert_called_once_with("secret")
    mock_user_repository.get_by_username.assert_awaited_once_with(username="agent")
    assert mock_uow.session is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user", "password_ok"),
    [
        (None, False),
        (
            User(
                id=7,
                username="inactive",
                password="hashed-password",
                email="inactive@test.com",
                is_active=False,
                is_admin=False,
            ),
            True,
        ),
        (
            User(
                id=7,
                username="agent",
                password="hashed-password",
                email="agent@test.com",
                is_active=True,
                is_admin=False,
            ),
            False,
        ),
    ],
)
async def test_authenticate_web_user_rejects_invalid_user(
    user: User | None,
    password_ok: bool,
    mock_user_repository: MagicMock,
    mock_uow: MagicMock,
) -> None:
    mock_user_repository.get_by_username.return_value = user

    with patch.object(User, "verify_password", return_value=password_ok):
        result = await authenticate_web_user(username="agent", password="wrong")

    assert result is None
    assert mock_uow.session is not None


def test_login_and_logout_only_manage_web_user_session(active_user: User) -> None:
    request = get_request(session={"old": "value"})

    login_web_user(request, active_user)
    assert request.session == {SESSION_USER_ID: active_user.id}

    logout_web_user(request)
    assert request.session == {}
