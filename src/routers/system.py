from datetime import datetime

from fastapi import APIRouter

from src.db.repositories import VendorRepository
from src.db.services import SASessionUOW
from src.models import SystemInfo, HealthCheck
from src.routers import ErrorHandlingBaseRoute

__all__ = ("router",)


router = APIRouter(
    prefix="/system",
    tags=["system"],
    responses={404: {"description": "Not found"}},
    route_class=ErrorHandlingBaseRoute,
)


@router.get("/info/", response_model=SystemInfo)
async def get_system_info() -> SystemInfo:
    """Get current system information."""

    async with SASessionUOW() as uow:
        vendor_repository = VendorRepository(session=uow.session)
        vendors = await vendor_repository.all()

    return SystemInfo(
        status="ok",
        providers=[vendor.name for vendor in vendors],
    )


@router.get("/health/", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(
        status="healthy",
        timestamp=datetime.now(),
    )
