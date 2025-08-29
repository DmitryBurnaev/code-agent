from datetime import datetime

from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories import VendorRepository
from src.db.services import SASessionUOW
from src.db.dependencies import get_db_session
from src.models import SystemInfo, HealthCheck
from src.modules.api import ErrorHandlingBaseRoute

__all__ = ("router",)


router = APIRouter(
    prefix="/system",
    tags=["system"],
    responses={404: {"description": "Not found"}},
    route_class=ErrorHandlingBaseRoute,
)


@router.get("/info/", response_model=SystemInfo)
async def get_system_info() -> SystemInfo:
    """Get current system information using SASessionUOW (legacy approach)."""

    async with SASessionUOW() as uow:
        vendor_repository = VendorRepository(session=uow.session)
        vendors = await vendor_repository.all()

    return SystemInfo(
        status="ok",
        vendors=[vendor.slug for vendor in vendors],
    )


@router.get("/info-new/", response_model=SystemInfo)
async def get_system_info_new(session: AsyncSession = Depends(get_db_session)) -> SystemInfo:
    """Get current system information using dependency injection (new approach)."""

    vendor_repository = VendorRepository(session=session)
    vendors = await vendor_repository.all()

    return SystemInfo(
        status="ok",
        vendors=[vendor.slug for vendor in vendors],
    )


@router.get("/health/", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(
        status="healthy",
        timestamp=datetime.now(),
    )
