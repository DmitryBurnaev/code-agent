from typing import Annotated

from fastapi import Depends, HTTPException, Request

from src.modules.auth.tokens import verify_api_token, authenticate_api_token, AuthenticatedAPIToken
from src.modules.auth.permissions import Permission, has_permission
from src.db.models import User
from src.modules.web import auth as web_auth

__all__ = ("verify_api_token", "APIAccess", "WebAccess")


class APIAccess:
    """An enforcing, introspectable feature policy for token-authenticated APIs."""

    def __init__(self, permission: Permission) -> None:
        self.permission = permission

    async def __call__(
        self,
        request: Request,
        authentication: Annotated[AuthenticatedAPIToken, Depends(authenticate_api_token)],
    ) -> None:
        if request.method == "OPTIONS":
            return
        if not has_permission(authentication.user, self.permission):
            raise HTTPException(status_code=403, detail="Permission denied")


class WebAccess:
    """Authorize the current browser user and return it for endpoint injection."""

    def __init__(self, permission: Permission | None = None) -> None:
        self.permission = permission

    async def __call__(self, request: Request) -> User:
        user = await web_auth.get_current_web_user(request)
        if user is None:
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        if not user.is_active or (
            self.permission is not None and not has_permission(user, self.permission)
        ):
            raise HTTPException(status_code=403, detail="Permission denied")
        return user
