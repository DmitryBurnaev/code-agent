import dataclasses

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories import VendorRepository


@dataclasses.dataclass(frozen=True)
class DashboardCounts:
    total_vendors: int
    active_vendors: int


class AdminCounter:
    """Admin's dashboard aggregations"""

    @classmethod
    async def get_stat(cls, session: AsyncSession) -> DashboardCounts:
        """Get vendors counts"""
        vendor_repository = VendorRepository(session)
        active_vendors = await vendor_repository.group_by_active()
        return DashboardCounts(
            total_vendors=active_vendors["active"] + active_vendors["inactive"],
            active_vendors=active_vendors["active"],
        )
