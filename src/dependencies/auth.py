from typing import cast

from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader
from sqladmin.authentication import AuthenticationBackend

from src.db.models import User
from src.db.repositories import UserRepository
from src.db.services import SASessionUOW
from src.dependencies import SettingsDep

__all__ = ["verify_api_token"]


api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_token(
    request: Request,
    settings: SettingsDep,
    auth_token: str | None = Security(api_key_header),
) -> str:
    """
    Verify the authentication token from the header.
    Skip verification for OPTIONS methods.
    """
    if request.method == "OPTIONS":
        return ""

    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_token = auth_token.replace("Bearer ", "").strip()
    if auth_token != settings.api_token.get_secret_value():
        raise HTTPException(status_code=403, detail="Invalid authentication token")

    return auth_token


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username: str = cast(str, form["username"])
        password: str = cast(str, form["password"])

        async with SASessionUOW() as uow:
            user = await UserRepository(session=uow.session).get_by_username(username=username)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            password_verified = user.verify_password(password)

        if not password_verified:
            raise HTTPException(status_code=403, detail="Invalid password")

        # TODO: use Token model here
        request.session.update({"token": "..."})
        return True

    async def logout(self, request: Request) -> bool:
        # Usually you'd want to just clear the session
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")

        if not token:
            return False

        # TODO: Check the real token here
        return True
