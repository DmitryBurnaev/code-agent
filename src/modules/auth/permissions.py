"""Feature permissions shared by API, admin, and browser authorization."""

from enum import StrEnum
from typing import Protocol


class Permission(StrEnum):
    ADMIN_PANEL = "can_access_admin"
    SYSTEM_API = "can_access_system_api"
    LLM = "can_use_llm"
    TIME_TRACKING = "can_use_time_tracking"
    BILLING = "can_access_billing"


class PermissionUser(Protocol):
    is_active: bool
    is_admin: bool


def has_permission(user: PermissionUser | None, permission: Permission) -> bool:
    """Active superusers pass every check; other users need the explicit flag."""
    return (
        user is not None
        and user.is_active is True
        and (user.is_admin is True or getattr(user, permission.value, False) is True)
    )
