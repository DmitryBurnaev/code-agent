from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader

from src.dependencies import SettingsDep

__all__ = ["verify_api_token"]


api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_token(
    request: Request,
    settings: SettingsDep,
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
    if auth_token != settings.auth_api_token.get_secret_value():
        raise HTTPException(status_code=403, detail="Invalid authentication token")

    return auth_token
