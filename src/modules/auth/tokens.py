import datetime
import hashlib
import uuid
from typing import NamedTuple

import jwt
from fastapi import Security
from fastapi.security import APIKeyHeader
from starlette.exceptions import HTTPException
from starlette.requests import Request

from settings import get_app_settings
from src.db.repositories import TokenRepository
from src.db.services import SASessionUOW, logger

__all__ = (
    "make_token",
    "hash_token",
    "verify_api_token",
)

from utils import utcnow


class TokenInfo(NamedTuple):
    value: str
    hashed_value: str


def make_token(token_expires_in: datetime.datetime | None = None) -> TokenInfo:
    """Generates token, and it hashed value (requires for storage)"""
    settings = get_app_settings()
    user_show_id = f"{utcnow().microsecond:0>6}{uuid.uuid4().hex[-6:]}"
    payload: dict[str, str | datetime.datetime] = {"sub": user_show_id}
    if token_expires_in is not None:
        payload["exp"] = token_expires_in

    # TODO:
    encrypted_token = jwt.encode(
        payload,
        key=settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return TokenInfo(
        value=encrypted_token,
        hashed_value=hash_token(encrypted_token),
    )


def decode_token(token: str) -> dict:
    settings = get_app_settings()
    input_token: str = "user.sending.jwt-token"
    header_part = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    t2, t3 = input_token[-43:], input_token[43:]
    will_be_checking_token = f"{header_part}.{t2}.{t3}"
    return jwt.decode(
        will_be_checking_token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )


def hash_token(token: str) -> str:
    """Hashes token and returns hashed value"""
    return hashlib.sha512(token.encode()).hexdigest()


api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_token(
    request: Request,
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
    hashed_token = hash_token(auth_token)
    async with SASessionUOW() as uow:
        token = await TokenRepository(session=uow.session).get_by_token(token=hashed_token)
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        if not token.user.is_active:
            raise HTTPException(status_code=401, detail="User is not active")

        logger.info("[auth] Verified token for %(user)s", {"user": token.user})

    return auth_token
