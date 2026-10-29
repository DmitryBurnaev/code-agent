from datetime import datetime

from fastapi import APIRouter, Depends

from src.db.repositories import VendorRepository
from src.db.services import SASessionUOW
from src.db.dependencies import get_uow_with_session
from src.models import SystemInfo, HealthCheck
from src.modules.api.base import ErrorHandlingBaseRoute
from src.modules.auth.dependencies import APIAccess
from src.modules.auth.permissions import Permission

__all__ = ("router",)


router = APIRouter(
    dependencies=[Depends(APIAccess(Permission.SYSTEM_API))],
    prefix="/system",
    tags=["system"],
    responses={404: {"description": "Not found"}},
    route_class=ErrorHandlingBaseRoute,
)


@router.get("/info/", response_model=SystemInfo)
async def get_system_info(uow: SASessionUOW = Depends(get_uow_with_session)) -> SystemInfo:
    """Get current system information using SASessionUOW (legacy approach)."""

    async with uow:
        vendor_repository = VendorRepository(session=uow.session)
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
