"""Session authentication helpers for browser-facing pages."""

from fastapi import Request

from src.db.models import User
from src.db.repositories import UserRepository
from src.db.services import SASessionUOW

SESSION_USER_ID = "web_user_id"


async def get_current_web_user(request: Request) -> User | None:
    """Return the active user stored in the browser session, if any."""
    user_id = request.session.get(SESSION_USER_ID)
    if type(user_id) is not int:
        return None

    async with SASessionUOW() as uow:
        user = await UserRepository(session=uow.session).first(instance_id=user_id)

    if user is None or not user.is_active:
        logout_web_user(request)
        return None

    return user


async def authenticate_web_user(username: str, password: str) -> User | None:
    """Validate browser login credentials for an active user."""
    async with SASessionUOW() as uow:
        user = await UserRepository(session=uow.session).get_by_username(username=username)

    if user is None or not user.is_active or not user.verify_password(password):
        return None

    return user


def login_web_user(request: Request, user: User) -> None:
    """Persist the authenticated user's id in the signed browser session."""
    request.session.clear()
    request.session[SESSION_USER_ID] = user.id


def logout_web_user(request: Request) -> None:
    """Clear the browser-facing application session."""
    request.session.clear()
