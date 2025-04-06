from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.settings import app_settings

api_key_header = APIKeyHeader(name="Authorization", auto_error=True)


async def verify_token(auth_token: str = Security(api_key_header)) -> str:
    """
    Verify the authentication token from the header.
    """
    auth_token = auth_token.replace("Bearer ", "").strip()
    if auth_token != app_settings.auth_api_token.get_secret_value():
        raise HTTPException(
            status_code=403,
            detail="Invalid authentication token",
        )
    return auth_token
