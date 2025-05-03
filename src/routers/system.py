from datetime import datetime

from fastapi import APIRouter

from src.dependencies import SettingsDep
from src.models import SystemInfo, HealthCheck

__all__ = ("router",)


router = APIRouter(
    prefix="/system",
    tags=["system"],
    responses={404: {"description": "Not found"}},
)


@router.get("/info/", response_model=SystemInfo)
async def get_system_info(settings: SettingsDep) -> SystemInfo:
    """Get current system information."""
    return SystemInfo(
        status="ok",
        providers=[provider.vendor for provider in settings.providers],
    )


@router.get("/health/", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(
        status="healthy",
        timestamp=datetime.now(),
    )
