import datetime
import logging
from typing import cast, TypedDict

from fastapi import HTTPException, Request
from sqladmin.authentication import AuthenticationBackend
from src.db.repositories import UserRepository
from src.db.services import SASessionUOW
from src.dependencies import SettingsDep
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

    def __init__(self, secret_key: str, settings: SettingsDep) -> None:
        super().__init__(secret_key=secret_key)
        self.settings: AppSettings = settings

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username: str = cast(str, form["username"])
        password: str = cast(str, form["password"])

        async with SASessionUOW() as uow:
            user = await UserRepository(session=uow.session).get_by_username(username=username)
            if not user:
                raise HTTPException(status_code=401, detail="User not found")

            if not user.is_active:
                raise HTTPException(status_code=401, detail="User inactive")

            password_verified = user.verify_password(password)

        if not password_verified:
            raise HTTPException(status_code=401, detail="Invalid password")

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

        user_id = self._decode_token(token)
        async with SASessionUOW() as uow:
            user = await UserRepository(session=uow.session).first(instance_id=user_id)
            if not user:
                logger.error("User 'id: %r' not found", user_id)
                return False

            if not user.is_active:
                logger.error("User '%r' inactive", user)
                return False

            if not user.is_admin:
                logger.error("User '%r' not admin", user)
                return False

        return True

    def _encode_token(self, user_payload: UserPayload) -> str:
        exp_time = self.settings.admin_session_expiration_time
        admin_login_token = jwt_encode(
            payload=JWTPayload(sub=str(user_payload["id"])),
            expires_at=(utcnow() + datetime.timedelta(seconds=exp_time)),
            settings=self.settings,
        )
        return admin_login_token

    def _decode_token(self, token: str) -> USER_ID:
        user_payload = jwt_decode(token, settings=self.settings)
        return int(user_payload.sub)
