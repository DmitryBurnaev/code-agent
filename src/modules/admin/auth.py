import base64
import json
import logging
from typing import cast, TypedDict, Any

from fastapi import HTTPException, Request
from sqladmin.authentication import AuthenticationBackend
from src.db.repositories import UserRepository
from src.db.services import SASessionUOW

logger = logging.getLogger(__name__)


class UserPayload(TypedDict):
    id: int
    username: str
    email: str


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

        user_payload: UserPayload = {"id": user.id, "username": user.username, "email": user.email}
        request.session.update({"token": self._encode_token(user_payload)})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")

        if not token:
            return False

        user_payload = json.loads(base64.b64decode(token).decode())
        async with SASessionUOW() as uow:
            user = await UserRepository(session=uow.session).first(instance_id=user_payload["id"])
            if not user:
                logger.error(f"User {user_payload['id']} not found")
                return False

        return True

    @classmethod
    def _encode_token(cls, user_payload: UserPayload) -> str:
        # TODO: use real JWT here
        fake_jwt_token: str = base64.b64encode(json.dumps(user_payload).encode()).decode()
        return fake_jwt_token

    @classmethod
    def _decode_token(cls, token: str) -> UserPayload:
        user_payload: dict[str, Any] = json.loads(base64.b64decode(token).decode())
        return UserPayload(
            id=user_payload["id"],
            username=user_payload["username"],
            email=user_payload["email"],
        )
