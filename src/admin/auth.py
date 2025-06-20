from typing import cast

from fastapi import HTTPException, Request
from sqladmin.authentication import AuthenticationBackend

from src.db.repositories import UserRepository
from src.db.services import SASessionUOW


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
