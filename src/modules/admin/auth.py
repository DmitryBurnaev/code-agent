import datetime
import logging
from typing import cast, TypedDict

import jwt
from fastapi import Request
from sqladmin.authentication import AuthenticationBackend

from src.db.repositories import UserRepository
from src.db.services import SASessionUOW
from src.db.models import User
from src.modules.auth.tokens import jwt_encode, JWTPayload, jwt_decode
from src.settings import AppSettings
from src.utils import utcnow

logger = logging.getLogger(__name__)
type USER_ID = int


class UserPayload(TypedDict):
    id: int
    username: str
    email: str


class AdminAuth(AuthenticationBackend):
    """
    Customized admin authentication (based on encoding JWT token based on current user)
    """

    def __init__(self, secret_key: str, settings: AppSettings) -> None:
        super().__init__(secret_key=secret_key)
        self.settings: AppSettings = settings

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username: str = cast(str, form["username"])
        password: str = cast(str, form["password"])

        async with SASessionUOW() as uow:
            user = await UserRepository(session=uow.session).get_by_username(username=username)
            ok, _ = self._check_user(user, identety=username, password=password)
            if not ok:
                return False

            admin: User = cast(User, user)

        payload: UserPayload = {"id": admin.id, "username": admin.username, "email": admin.email}
        request.session.update({"token": self._encode_token(payload)})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")

        if not token:
            return False

        user_id = self._decode_token(token)
        if not user_id:
            logger.warning("[admin-auth] Invalid or outdated session's token")
            return False

        async with SASessionUOW() as uow:
            user = await UserRepository(session=uow.session).first(instance_id=user_id)
            ok, _ = self._check_user(user, identety=user_id)
            if not ok:
                return False

        return True

    def _encode_token(self, user_payload: UserPayload) -> str:
        exp_time = self.settings.admin.session_expiration_time
        admin_login_token = jwt_encode(
            payload=JWTPayload(sub=str(user_payload["id"])),
            expires_at=(utcnow() + datetime.timedelta(seconds=exp_time)),
            settings=self.settings,
        )
        return admin_login_token

    def _decode_token(self, token: str) -> USER_ID | None:
        try:
            user_payload = jwt_decode(token, settings=self.settings)
        except jwt.PyJWTError:
            return None

        return int(user_payload.sub)

    @staticmethod
    def _check_user(user: User | None, identety: str | int,  password: str | None = None) -> tuple[bool, str]:
        if not user:
            logger.error("[admin-auth] User '%r' not found", identety)
            return False, "User not found"

        if password is not None:
            password_verified = user.verify_password(password)
            if not password_verified:
                logger.error("[admin-auth] User '%r' | invalid password", user)
                return False, "Invalid password"

        if not user.is_active:
            logger.error("[admin-auth] User '%r' | inactive", user)
            return False, "User inactive"

        if not user.is_admin:
            logger.error("[admin-auth] User '%r' | not an admin", user)
            return False, "User is not an admin"

        return True, "User is active"
