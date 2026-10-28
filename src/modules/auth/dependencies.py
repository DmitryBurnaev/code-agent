from typing import Annotated, Callable, Coroutine, Any

from fastapi import Depends, HTTPException, Request

from src.modules.auth.tokens import verify_api_token, authenticate_api_token, AuthenticatedAPIToken
from src.modules.auth.permissions import Permission, has_permission

__all__ = ("verify_api_token", "require_api_permission")

VerifyAPITokenDep = Depends(verify_api_token)


def require_api_permission(permission: Permission) -> Callable[..., Coroutine[Any, Any, None]]:
    """Authenticate once per request and authorize the token's current owner."""

    async def check_permission(
        request: Request,
        authentication: Annotated[AuthenticatedAPIToken, Depends(authenticate_api_token)],
    ) -> None:
        if request.method == "OPTIONS":
            return
        if not has_permission(authentication.user, permission):
            raise HTTPException(status_code=403, detail="Permission denied")

    return check_permission
