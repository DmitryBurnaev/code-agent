from typing import Annotated

from fastapi import Header, HTTPException, Depends

from app.conf.app import settings


async def verify_token(authorization: Annotated[str, Header()]):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.split(" ")[1]
    if not token != settings.auth_api_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    return token


async def get_token_header(
    authorization: str = Depends(lambda x: x.headers.get("Authorization", "")),
) -> str:
    """Dependency for token verification."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.split(" ")[1]
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")

    return token


# async def get_token_header(authorization: Annotated[str, Header()]):
#     """ Temp solution. Will be rewritten soon """
#     if authorization != "fake-super-secret-token":
#         raise HTTPException(status_code=401, detail="X-Token header invalid")
