"""DB-specific module that provides specific operations on the database."""

import logging
from typing import (
    Generic,
    TypeVar,
    Any,
    TypedDict,
    Sequence,
    # Unpack,
    ParamSpec,
)

from sqlalchemy import select, BinaryExpression, delete
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BaseModel, Vendor

ModelT = TypeVar("ModelT", bound=BaseModel)
logger = logging.getLogger(__name__)
P = ParamSpec("P")
RT = TypeVar("RT")


class VendorsFilter(TypedDict):
    """Simple structure to filter users by specific params"""

    ids: list[int] | None
    slug: str | None


class BaseRepository(Generic[ModelT]):
    """
    Base repository interface.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    async def get(self, instance_id: int) -> ModelT:
        """Selects instance by provided ID"""
        instance: ModelT | None = await self.first(instance_id)
        if not instance:
            raise NoResultFound

        return instance

    async def first(self, instance_id: int) -> ModelT | None:
        """Selects instance by provided ID"""
        statement = select(self.model).filter_by(id=instance_id)
        result = await self.session.execute(statement)
        row: Sequence[ModelT] | None = result.fetchone()
        if not row:
            return None

        return row[0]

    async def all(self, **filters: int | str | list[int] | None) -> list[ModelT]:
        """Selects instances from DB"""
        filters_stmts: list[BinaryExpression[bool]] = []
        if (ids := filters.pop("ids", None)) and isinstance(ids, list):
            filters_stmts.append(self.model.id.in_(ids))

        statement = select(self.model).filter_by(**filters)
        if filters_stmts:
            statement = statement.filter(*filters_stmts)

        result = await self.session.execute(statement)
        return [row[0] for row in result.fetchall()]

    async def create(self, value: dict[str, Any]) -> ModelT:
        """Creates new instance"""
        logger.debug("[DB] Creating [%s]: %s", self.model.__name__, value)
        instance = self.model(**value)
        self.session.add(instance)
        return instance

    async def get_or_create(self, id_: int, value: dict[str, Any]) -> ModelT:
        """Tries to find an instance by ID and create if it wasn't found"""
        instance = await self.first(id_)
        if instance is None:
            await self.create(value | {"id": id_})
            instance = await self.get(id_)

        return instance

    async def update(self, instance: ModelT, **value: dict[str, Any]) -> None:
        """Just updates the instance with provided update_value."""
        for key, value in value.items():
            setattr(instance, key, value)

        self.session.add(instance)

    async def delete(self, instance: ModelT) -> None:
        """Remove the instance from the DB."""
        await self.session.delete(instance)

    async def delete_by_ids(self, removing_ids: Sequence[int]) -> None:
        """Remove the instances from the DB."""
        statement = delete(self.model).filter(self.model.id.in_(removing_ids))
        await self.session.execute(statement)


class VendorRepository(BaseRepository[Vendor]):
    """User's repository."""

    model = Vendor

    async def filter(
        self,
        ids: Sequence[int] | None = None,
        slug: str | None = None,
    ) -> list[Vendor]:
        """Extra filtering vendors by some parameters."""
        filters: dict[str, Any] = {}
        if slug:
            filters["slug"] = slug
        if ids:
            filters["ids"] = ids

        return await self.all(**filters)


# class VendorSettingsRepository(BaseRepository[VendorSettings]):
#     model = VendorSettings
#
#     async def filter(self, **filters: Unpack[VendorsFilter]) -> list[VendorSettings]:
#         """Extra filtering ve by some parameters."""
#         return await self.all(**filters)


# class VendorRepository:
#     """Repository for vendor operations."""
#
#     def __init__(self, session: AsyncSession):
#         self.session = session
#
#     async def create_vendor(
#         self,
#         name: str,
#         encrypted_api_key: str,
#         public_key: str,
#         url: Optional[str] = None,
#         auth_type: str = "Bearer",
#         timeout: int = 30,
#     ) -> Vendor:
#         """Create a new vendor with settings."""
#         vendor = Vendor(
#             name=name,
#             url=url,
#             auth_type=auth_type,
#             timeout=timeout,
#         )
#         self.session.add(vendor)
#         await self.session.flush()
#
#         settings = VendorSettings(
#             vendor_id=vendor.id,
#             encrypted_api_key=encrypted_api_key,
#             public_key=public_key,
#         )
#         self.session.add(settings)
#         await self.session.commit()
#
#         return vendor
#
#     async def get_vendor_by_name(self, name: str) -> Optional[Vendor]:
#         """Get vendor by name."""
#         query = select(Vendor).where(Vendor.name == name)
#         result = await self.session.execute(query)
#         return result.scalar_one_or_none()
#
#     async def get_vendor_with_settings(self, vendor_id: int) -> Optional[Vendor]:
#         """Get vendor with its settings."""
#         query = select(Vendor).where(Vendor.id == vendor_id)
#         result = await self.session.execute(query)
#         return result.scalar_one_or_none()
#
#     async def get_all_vendors(self) -> List[Vendor]:
#         """Get all active vendors."""
#         query = select(Vendor).where(Vendor.is_active == True)
#         result = await self.session.execute(query)
#         return list(result.scalars().all())
#
#     async def update_vendor_settings(
#         self, vendor_id: int, encrypted_api_key: str, public_key: str
#     ) -> Optional[VendorSettings]:
#         """Update vendor settings."""
#         query = select(VendorSettings).where(VendorSettings.vendor_id == vendor_id)
#         result = await self.session.execute(query)
#         settings = result.scalar_one_or_none()
#
#         if settings:
#             settings.encrypted_api_key = encrypted_api_key
#             settings.public_key = public_key
#             await self.session.commit()
#
#         return settings
#
#     async def delete_vendor(self, vendor_id: int) -> bool:
#         """Delete vendor and its settings."""
#         query = select(Vendor).where(Vendor.id == vendor_id)
#         result = await self.session.execute(query)
#         vendor = result.scalar_one_or_none()
#
#         if vendor:
#             await self.session.delete(vendor)
#             await self.session.commit()
#             return True
#
#         return False
