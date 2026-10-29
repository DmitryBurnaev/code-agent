"""Feature permissions shared by API, admin, and browser authorization."""

from enum import StrEnum
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping
from typing import Protocol


class Permission(StrEnum):
    ADMIN_PANEL = "can_access_admin"
    SYSTEM_API = "can_access_system_api"
    LLM = "can_use_llm"
    TIME_TRACKING = "can_use_time_tracking"
    BILLING = "can_access_billing"


@dataclass(frozen=True)
class PermissionDefinition:
    label: str
    description: str


PERMISSION_DEFINITIONS: Mapping[Permission, PermissionDefinition] = MappingProxyType(
    {
        Permission.ADMIN_PANEL: PermissionDefinition(
            "Admin Panel", "Access administration and manage users and their permissions."
        ),
        Permission.SYSTEM_API: PermissionDefinition(
            "System API", "Access system health and information."
        ),
        Permission.LLM: PermissionDefinition(
            "LLM", "Use model listing, chat completions and cancellation."
        ),
        Permission.TIME_TRACKING: PermissionDefinition(
            "Time Tracking", "Use the tracker, timers, entries and tracking widgets."
        ),
        Permission.BILLING: PermissionDefinition(
            "Billing", "Access the balance API and balance widget."
        ),
    }
)


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
