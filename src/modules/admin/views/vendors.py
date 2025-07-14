import logging
from typing import cast, Any

from fastapi import HTTPException
from starlette.requests import Request

from src.modules.admin.views.base import FormDataType, BaseModelView
from src.db.models import BaseModel, Vendor
from src.db.repositories import VendorRepository
from src.db.services import SASessionUOW
from src.utils import admin_get_link, simple_slugify
from src.modules.auth.encryption import VendorKeyEncryption
from src.settings import get_app_settings

__all__ = ("VendorAdminView",)
logger = logging.getLogger(__name__)


class VendorAdminView(BaseModelView, model=Vendor):
    icon = "fa-solid fa-box-archive"
    column_list = (Vendor.id, Vendor.api_url, Vendor.is_active)
    column_formatters = {Vendor.id: lambda model, a: admin_get_link(cast(BaseModel, model))}
    form_columns = (
        Vendor.slug,
        Vendor.api_url,
        Vendor.api_key,
        Vendor.timeout,
        Vendor.is_active,
    )
    column_details_list = (
        Vendor.id,
        Vendor.slug,
        Vendor.api_url,
        Vendor.timeout,
        Vendor.is_active,
        Vendor.created_at,
        Vendor.updated_at,
    )
    column_labels = {
        Vendor.slug: "Slug",
        Vendor.api_url: "API URL",
        Vendor.api_key: "API Key",
        Vendor.timeout: "Timeout",
        Vendor.is_active: "Is Active",
    }

    async def insert_model(self, request: Request, data: FormDataType) -> Any:
        data = await self._validate(data)
        # Encrypt API key before saving
        if "api_key" in data and data["api_key"]:
            data["api_key"] = self._encrypt_api_key(data["api_key"])
        return await super().insert_model(request, data)

    async def update_model(self, request: Request, pk: str, data: FormDataType) -> Any:
        data = await self._validate(data, vendor_id=int(pk))
        # Encrypt API key before saving if provided
        if "api_key" in data and data["api_key"]:
            data["api_key"] = self._encrypt_api_key(data["api_key"])
        return await super().update_model(request, pk, data)

    @staticmethod
    def _encrypt_api_key(plaintext_key: str) -> str:
        """Encrypt API key using application encryption settings.
        
        Args:
            plaintext_key: Plaintext API key to encrypt
            
        Returns:
            Encrypted API key
            
        Raises:
            ValueError: If encryption fails or key is empty
        """
        if not plaintext_key:
            raise ValueError("API key cannot be empty")
            
        try:
            settings = get_app_settings()
            encryption = VendorKeyEncryption(settings.vendor_encryption_key)
            return encryption.encrypt(plaintext_key)
        except Exception as exc:
            logger.error("Failed to encrypt API key: %s", exc)
            raise ValueError("Failed to encrypt API key") from exc

    @classmethod
    async def _validate(cls, data: FormDataType, vendor_id: int | None = None) -> FormDataType:
        slug = data.pop("slug", None)
        if not slug:
            raise HTTPException(status_code=400, detail="Slug required")

        validated_slug = await cls._validate_slug(slug=str(slug), vendor_id=vendor_id)
        if validated_slug:
            data["slug"] = validated_slug

        return data

    @classmethod
    async def _validate_slug(cls, slug: str, vendor_id: int | None = None) -> str | None:
        slug = simple_slugify(slug)
        async with SASessionUOW() as uow:
            vendor_repository = VendorRepository(uow.session)
            current_vendor: Vendor | None = None
            if vendor_id is not None:
                current_vendor = await vendor_repository.get(vendor_id)

            if current_vendor and current_vendor.slug == slug:
                logger.debug("[Admin] Vendor slug has the same slug")
                return None

            exists_vendors = await vendor_repository.filter(slug=slug)
            if current_vendor:
                exists_vendors = [
                    vendor for vendor in exists_vendors if vendor.id != current_vendor.id
                ]

            if exists_vendors:
                raise HTTPException(
                    status_code=400, detail=f"Vendor with slug '{slug}' already exists"
                )

        return slug
