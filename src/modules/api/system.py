from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories import VendorRepository, UserRepository, TokenRepository
from src.db.services import SASessionUOW
from src.db.dependencies import get_db_session, get_uow_with_session
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


@router.get("/info-uow-di/", response_model=SystemInfo)
async def get_system_info_uow_di(uow: SASessionUOW = Depends(get_uow_with_session)) -> SystemInfo:
    """
    Get current system information using UOW with dependency injection.
    
    This demonstrates the hybrid approach: dependency injection for session lifecycle,
    UOW for transaction control (even though this is a simple read operation).
    """

    async with uow:
        vendor_repository = VendorRepository(session=uow.session)
        vendors = await vendor_repository.all()
        # For read operations, no commit needed
        # uow.mark_for_commit()  # Would be used for write operations

    return SystemInfo(
        status="ok",
        vendors=[vendor.slug for vendor in vendors],
    )


@router.post("/complex-operation/")
async def complex_atomic_operation(uow: SASessionUOW = Depends(get_uow_with_session)) -> dict:
    """
    Example of complex atomic operation using UOW with dependency injection.
    
    This demonstrates how to perform multiple database operations in a single transaction
    with explicit control over commit/rollback using repositories.
    """
    
    async with uow:
        try:
            # Multiple operations that should be atomic using repositories
            vendor_repo = VendorRepository(session=uow.session)
            user_repo = UserRepository(session=uow.session)
            token_repo = TokenRepository(session=uow.session)
            
            # Simulate some complex business logic
            vendors = await vendor_repo.all()
            users = await user_repo.all()
            tokens = await token_repo.all()
            
            # If any condition fails, the entire transaction should be rolled back
            if len(vendors) == 0:
                raise HTTPException(status_code=400, detail="No vendors available")
            
            if len(users) == 0:
                raise HTTPException(status_code=400, detail="No users available")
            
            # All operations succeeded - mark for commit
            uow.mark_for_commit()
            
            return {
                "status": "success",
                "vendors_count": len(vendors),
                "users_count": len(users),
                "tokens_count": len(tokens),
                "message": "All operations completed atomically"
            }
            
        except Exception as e:
            # Transaction will be automatically rolled back due to exception
            # No need to explicitly call uow.rollback()
            raise e


@router.get("/health/", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(
        status="healthy",
        timestamp=datetime.now(),
    )
