import dataclasses
import uuid
import random
import hashlib
import datetime
from typing import NamedTuple

import jwt
from fastapi import Security
from fastapi.security import APIKeyHeader
from starlette.exceptions import HTTPException
from starlette.requests import Request

from src.settings import get_app_settings
from src.db.repositories import TokenRepository
from src.db.services import SASessionUOW, logger

__all__ = (
    "make_token",
    "hash_token",
    "verify_api_token",
)
SIGNATURE_LENGTH = 43  # based


class TokenInfo(NamedTuple):
    value: str
    hashed_value: str


@dataclasses.dataclass
class PayloadTokenInfo:
    sub: str
    exp: datetime.datetime

    def as_dict(self) -> dict[str, str | datetime.datetime]:
        return dataclasses.asdict(self)


def make_token(expires_at: datetime.datetime | None = None) -> TokenInfo:
    """
    Generates token, and it hashed value (requires for storage).
    Token is a custom formatted JWT token (without header part).

    Removing header allows simplifying token usage by client.
    For verification, we can use just payload part and signature part.

    Parameters:
        expires_at: datetime.datetime | None - expiration time of the token

    Returns:
        TokenInfo - tuple of token and its hashed value
    """
    settings = get_app_settings()
    expires_at = expires_at or datetime.datetime.max
    token_identifier = f"{random.randint(100, 999):0>3}{uuid.uuid4().hex[-6:]}"
    payload_info = PayloadTokenInfo(sub=token_identifier, exp=expires_at)
    encrypted_token = jwt.encode(
        payload_info.as_dict(),
        key=settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    _, payload_part, signature_part = encrypted_token.split(".")
    result_value = f"{payload_part}{signature_part}"

    return TokenInfo(value=result_value, hashed_value=hash_token(token_identifier))


def decode_token(token: str) -> PayloadTokenInfo:
    """
    Decodes custom formatted JWT token (without header part).

    Parameters:
        token: str - token to decode

    Returns:
        PayloadTokenInfo - payload of the token
    """
    settings = get_app_settings()
    just_for_header_token = jwt.encode(
        {"sub": "example"},
        key=settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    header_part, _, _ = just_for_header_token.split(".")
    payload_part, signature_part = token[:-SIGNATURE_LENGTH], token[-SIGNATURE_LENGTH:]

    checking_token = f"{header_part}.{payload_part}.{signature_part}"
    logger.debug("[auth] JWT decoding token: %s", checking_token)

    try:
        payload = jwt.decode(
            checking_token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("exp") is None:
        raise HTTPException(status_code=401, detail="Token has no expiration time")

    logger.debug("[auth] Got payload: %s", payload)
    return PayloadTokenInfo(sub=payload["sub"], exp=payload.get("exp"))


def hash_token(token: str) -> str:
    """
    Hashes token and returns hashed value.

    Parameters:
        token: str - token to hash

    Returns:
        str - hashed value of the token (SHA-512)
    """
    return hashlib.sha512(token.encode()).hexdigest()


async def verify_api_token(
    request: Request,
    auth_token: str | None = Security(APIKeyHeader(name="Authorization", auto_error=False)),
) -> str:
    """
    Dependency for authentication by API token (placed in the header 'Authorization').
    Skip verification for OPTIONS methods.
    """
    if request.method == "OPTIONS":
        return ""

    if not auth_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    logger.debug("[auth] Authentication: input auth token: %s", auth_token)

    auth_token = auth_token.replace("Bearer ", "").strip()
    decoded_payload = decode_token(auth_token)
    raw_token_identity = decoded_payload.sub
    if not raw_token_identity:
        raise HTTPException(status_code=401, detail="Not authenticated: token has no identity")

    hashed_token = hash_token(raw_token_identity)

    async with SASessionUOW() as uow:
        token = await TokenRepository(session=uow.session).get_by_token(hashed_token)
        logger.info("[auth] Verification: token extracted '%s'", token)
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated: unknown token")

        if not token.is_active:
            raise HTTPException(status_code=401, detail="Not authenticated: inactive token")

        if not token.user.is_active:
            raise HTTPException(status_code=401, detail="Not authenticated: user is not active")

        logger.info("[auth] Verified token for %(user)s", {"user": token.user})

    return auth_token
