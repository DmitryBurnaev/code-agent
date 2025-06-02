from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Vendor, VendorSettings


class VendorRepository:
    """Repository for vendor operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_vendor(
        self,
        name: str,
        encrypted_api_key: str,
        public_key: str,
        url: Optional[str] = None,
        auth_type: str = "Bearer",
        timeout: int = 30,
    ) -> Vendor:
        """Create a new vendor with settings."""
        vendor = Vendor(
            name=name,
            url=url,
            auth_type=auth_type,
            timeout=timeout,
        )
        self.session.add(vendor)
        await self.session.flush()

        settings = VendorSettings(
            vendor_id=vendor.id,
            encrypted_api_key=encrypted_api_key,
            public_key=public_key,
        )
        self.session.add(settings)
        await self.session.commit()

        return vendor

    async def get_vendor_by_name(self, name: str) -> Optional[Vendor]:
        """Get vendor by name."""
        query = select(Vendor).where(Vendor.name == name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_vendor_with_settings(self, vendor_id: int) -> Optional[Vendor]:
        """Get vendor with its settings."""
        query = select(Vendor).where(Vendor.id == vendor_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all_vendors(self) -> List[Vendor]:
        """Get all active vendors."""
        query = select(Vendor).where(Vendor.is_active == True)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_vendor_settings(
        self, vendor_id: int, encrypted_api_key: str, public_key: str
    ) -> Optional[VendorSettings]:
        """Update vendor settings."""
        query = select(VendorSettings).where(VendorSettings.vendor_id == vendor_id)
        result = await self.session.execute(query)
        settings = result.scalar_one_or_none()

        if settings:
            settings.encrypted_api_key = encrypted_api_key
            settings.public_key = public_key
            await self.session.commit()

        return settings

    async def delete_vendor(self, vendor_id: int) -> bool:
        """Delete vendor and its settings."""
        query = select(Vendor).where(Vendor.id == vendor_id)
        result = await self.session.execute(query)
        vendor = result.scalar_one_or_none()

        if vendor:
            await self.session.delete(vendor)
            await self.session.commit()
            return True

        return False
