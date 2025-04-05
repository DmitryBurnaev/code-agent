import platform
from datetime import datetime

from fastapi import APIRouter, Depends

from app.dependencies.auth import verify_token
from app.models import SystemInfo, HealthCheck

__all__ = ["router"]


router = APIRouter(
    prefix="/system",
    tags=["system"],
    # dependencies=[Depends(get_token_header)],
    responses={404: {"description": "Not found"}},
)


@router.get("/info/", response_model=SystemInfo)
async def get_system_info(_: str = Depends(verify_token)) -> SystemInfo:
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
