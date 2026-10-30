"""Adapt feature flags to SQLAdmin's built-in grant authorization."""

from sqladmin.application import BaseAdmin
from sqladmin.authorization import GrantsAuthorizationBackend
from starlette.requests import Request

from src.modules.auth.permissions import Permission, has_permission


class FeatureAuthorization(GrantsAuthorizationBackend):
    admin: BaseAdmin

    def setup(self, admin: BaseAdmin) -> None:
        self.admin = admin

    async def get_grants(self, request: Request) -> set[tuple[str, str]]:
        user = getattr(request.state, "admin_user", None)
        if not has_permission(user, Permission.ADMIN_PANEL):
            return set()
        return {
            (view.identity, "*")
            for view in self.admin.views
            if has_permission(user, getattr(view, "required_permission"))
        }
