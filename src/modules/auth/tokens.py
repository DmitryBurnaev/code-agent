import hashlib
import uuid
from typing import NamedTuple

from fastapi import Security
from fastapi.security import APIKeyHeader
from starlette.exceptions import HTTPException
from starlette.requests import Request

from src.db.repositories import TokenRepository
from src.db.services import SASessionUOW, logger

__all__ = (
    "make_token",
    "hash_token",
    "verify_api_token",
)


class TokenInfo(NamedTuple):
    value: str
    hashed_value: str


def make_token() -> TokenInfo:
    """Generates token, and it hashed value (requires for storage)"""
    token = uuid.uuid4().hex
    hashed_token = hash_token(token)
    return TokenInfo(value=token, hashed_value=hashed_token)


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
