from typing import Annotated

from fastapi import Header, HTTPException

from app.settings import app_settings


async def verify_token(authorization: Annotated[str, Header()]):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.split(" ")[1]
    if token != app_settings.service_api_key:
        raise HTTPException(status_code=401, detail="Invalid token")

    return token
