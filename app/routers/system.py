import platform
from datetime import datetime

from fastapi import APIRouter, Depends

from app.models import SystemInfo, HealthCheck
from app.dependencies.auth import verify_token

__all__ = ["router"]


router = APIRouter(
    prefix="/system",
    tags=["system"],
    responses={404: {"description": "Not found"}},
)


@router.get("/info/", response_model=SystemInfo)
async def get_system_info() -> SystemInfo:
    """Get current system information."""
    return SystemInfo(
        current_time=datetime.now(),
        os_version=platform.platform(),
    )


@router.get("/health/", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(
        status="healthy",
        timestamp=datetime.now(),
    )
