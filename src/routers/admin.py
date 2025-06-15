import logging
from typing import cast, Any, Mapping, Sequence

from fastapi import HTTPException
from sqladmin import ModelView
from starlette.requests import Request
from wtforms import Form, StringField, EmailField, PasswordField, BooleanField

from src.constants import RENDER_KW
from src.db.models import BaseModel, User, Vendor
from src.db.repositories import VendorRepository
from src.db.services import SASessionUOW
from src.utils import admin_get_link, simple_slugify


logger = logging.getLogger(__name__)
type FormDataType = dict[str, str | int | None]


class BaseModelView(ModelView):
    can_export = False
    is_async = True


class UserAdminForm(Form):
    """Provides extra validation for users' creation/updating"""

    username = StringField(render_kw=RENDER_KW, label="Username")
    email = EmailField(render_kw=RENDER_KW)
    new_password = PasswordField(render_kw={"class": "form-control"}, label="New Password")
    repeat_password = PasswordField(
        render_kw={"class": "form-control"}, label="Repeat New Password"
    )
    is_admin = BooleanField(render_kw={"class": "form-check-input"})
    is_active = BooleanField(render_kw={"class": "form-check-input"})

    def validate(self, extra_validators: Mapping[str, Sequence[Any]] | None = None) -> bool:
        """Extra validation for user's form"""
        if new_password := self.data.get("new_password"):
            if new_password != self.data["repeat_password"]:
                self.new_password.errors = ("Passwords must be the same",)
                self.repeat_password.errors = ("Passwords must be the same",)
                return False

        return True


class UserAdmin(BaseModelView, model=User):
    form = UserAdminForm
    icon = "fa-solid fa-person-drowning"
    column_list = (User.id, User.username)
    column_details_list = (User.id, User.username, User.email)
    column_formatters = {User.username: lambda model, a: admin_get_link(cast(BaseModel, model))}

    async def insert_model(self, request: Request, data: FormDataType) -> Any:
        raw_password = data.pop("new_password", None)
        if raw_password:
            data["password"] = User.make_password(str(raw_password))
        else:
            raise HTTPException(status_code=400, detail="Password required")

        return await super().insert_model(request, data)

    async def update_model(self, request: Request, pk: str, data: FormDataType) -> Any:
        raw_password = data.pop("new_password", None)
        if raw_password:
            data["password"] = User.make_password(str(raw_password))

        return await super().update_model(request, pk, data)


class VendorAdmin(BaseModelView, model=Vendor):
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
        return await super().insert_model(request, data)

    async def update_model(self, request: Request, pk: str, data: FormDataType) -> Any:
        data = await self._validate(data, vendor_id=int(pk))
        return await super().update_model(request, pk, data)

    @classmethod
    async def _validate(
        cls,
        data: dict[str, str | int | None],
        vendor_id: int | None = None,
    ) -> dict[str, str | int | None]:
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


#
# class VendorSettingsAdmin(BaseModelView, model=VendorSettings):
#     name = "Vendor Access"
#     name_plural = name
#     column_list = (VendorSettings.id,)
#     icon = "fa-solid fa-list-squares"
#     form_columns = (
#         VendorSettings.vendor,
#         VendorSettings.api_key,
#     )
#     column_formatters = {
#         VendorSettings.id: lambda model, a: admin_get_link(
#             cast(BaseModel, model), url_name="vendor-settings"
#         )
#     }
