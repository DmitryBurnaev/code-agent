import dataclasses
import uuid
import random
import hashlib
import datetime
from typing import NamedTuple, cast

import jwt
from fastapi import Security
from fastapi.security import APIKeyHeader
from starlette.exceptions import HTTPException
from starlette.requests import Request

from src.settings import SettingsDep
from src.db.repositories import TokenRepository
from src.db.services import SASessionUOW, logger

__all__ = (
    "make_api_token",
    "hash_token",
    "verify_api_token",
)
SIGNATURE_LENGTH = 43  # based on algorithm
type JWT_PAYLOAD_RAW_T = dict[str, str | int | datetime.datetime]


class GeneratedToken(NamedTuple):
    value: str
    hashed_value: str


@dataclasses.dataclass
class JWTPayload:
    sub: str
    exp: datetime.datetime | None = None

    def as_dict(self) -> JWT_PAYLOAD_RAW_T:
        return dataclasses.asdict(self)


def jwt_encode(
    payload: JWTPayload,
    settings: SettingsDep,
    expires_at: datetime.datetime | None = None,
) -> str:
    """
    Generates signed JWT token with specified expiration datetime.
    """
    if expires_at is not None:
        payload.exp = expires_at

    encrypted_token = jwt.encode(
        payload.as_dict(),
        key=settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return encrypted_token


def jwt_decode(jwt_token: str, settings: SettingsDep) -> JWTPayload:
    """
    Returns decoded JWT payload.
    """
    try:
        payload: JWT_PAYLOAD_RAW_T = jwt.decode(
            jwt_token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return JWTPayload(
        sub=str(payload["sub"]),
        exp=cast(datetime.datetime, payload["exp"]),
    )


def make_api_token(
    expires_at: datetime.datetime | None,
    settings: SettingsDep,
) -> GeneratedToken:
    """
    Generates token, and it hashed value (requires for storage).
    Token is a custom formatted JWT token (without header part).

    Removing header allows simplifying token usage by client.
    For verification, we can use just payload part and signature part.

    Parameters:
        expires_at: datetime.datetime - expiration time of the token
        settings: Current settings

    Returns:
        TokenInfo - tuple of token and its hashed value
    """
    expires_at = expires_at or datetime.datetime.max
    token_identifier = f"{random.randint(100, 999):0>3}{uuid.uuid4().hex[-6:]}"
    encrypted_token = jwt_encode(
        payload=JWTPayload(sub=token_identifier, exp=expires_at),
        expires_at=expires_at,
        settings=settings,
    )
    _, payload_part, signature_part = encrypted_token.split(".")
    result_value = f"{payload_part}{signature_part}"
    if len(signature_part) != SIGNATURE_LENGTH:
        logger.warning("[auth] Generated token has wrong signature length: %d", len(signature_part))
        raise HTTPException(status_code=401, detail="Invalid generated signature (length mismatch)")

    return GeneratedToken(value=result_value, hashed_value=hash_token(token_identifier))


def decode_api_token(token: str, settings: SettingsDep) -> JWTPayload:
    """
    Decodes custom formatted JWT token (without header part).

    Parameters:
        token: str - token to decode
        settings: AppSettings - settings instance

    Returns:
        PayloadTokenInfo - payload of the token
    """
    just_for_header_token = jwt_encode(payload=JWTPayload(sub="example"), settings=settings)
    header_part, _, _ = just_for_header_token.split(".")
    payload_part, signature_part = token[:-SIGNATURE_LENGTH], token[-SIGNATURE_LENGTH:]

    checking_token = f"{header_part}.{payload_part}.{signature_part}"
    logger.debug("[auth] JWT decoding token: %s", checking_token)

    try:
        payload = jwt_decode(checking_token, settings=settings)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.exp is None:
        raise HTTPException(status_code=401, detail="Token has no expiration time")

    logger.debug("[auth] Got payload: %s", payload)
    return payload


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
    settings: SettingsDep,
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
    decoded_payload = decode_api_token(auth_token, settings=settings)
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
