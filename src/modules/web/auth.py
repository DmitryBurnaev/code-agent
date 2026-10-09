"""Session authentication helpers for browser-facing pages."""

import logging
from fastapi import Request

from src.db.models import User
from src.db.repositories import UserRepository
from src.db.services import SASessionUOW

SESSION_USER_ID = "web_user_id"
logger = logging.getLogger(__name__)


async def get_current_web_user(request: Request) -> User | None:
    """Return the active user stored in the browser session, if any."""
    user_id = request.session.get(SESSION_USER_ID)
    if type(user_id) is not int:
        logger.info(
            "[web-auth] Anonymous request: reason=%s",
            "missing_session_user_id" if user_id is None else "invalid_session_user_id_type",
        )
        return None

    async with SASessionUOW() as uow:
        user = await UserRepository(session=uow.session).first(instance_id=user_id)

    if user is None or not user.is_active:
        logger.warning(
            "[web-auth] Session rejected: user_id=%s reason=%s",
            user_id,
            "user_not_found" if user is None else "user_inactive",
        )
        logout_web_user(request)
        return None

    return user


async def authenticate_web_user(username: str, password: str) -> User | None:
    """Validate browser login credentials for an active user."""
    async with SASessionUOW() as uow:
        user = await UserRepository(session=uow.session).get_by_username(username=username)

    if user is None:
        logger.warning("[web-auth] Login rejected: reason=user_not_found")
        return None
    if not user.is_active:
        logger.warning("[web-auth] Login rejected: user_id=%s reason=user_inactive", user.id)
        return None
    if not user.verify_password(password):
        logger.warning("[web-auth] Login rejected: user_id=%s reason=invalid_password", user.id)
        return None

    return user


def login_web_user(request: Request, user: User) -> None:
    """Persist the authenticated user's id in the signed browser session."""
    logger.info("[web-auth] Login accepted: user_id=%s", user.id)
    request.session.clear()
    request.session[SESSION_USER_ID] = user.id


def logout_web_user(request: Request) -> None:
    """Clear the browser-facing application session."""
    request.session.clear()
