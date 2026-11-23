import logging
from typing import cast, Any

from fastapi import HTTPException
from sqladmin import expose
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from wtforms import Form, StringField, URLField, BooleanField, HiddenField

from src.settings import AppSettings, get_app_settings
from src.exceptions import VendorEncryptionError
from src.modules.admin.views.base import FormDataType, BaseModelView
from src.modules.encrypt.encryption import VendorKeyEncryption
from src.constants import RENDER_KW, RENDER_KW_REQ, VendorMode, VendorSlug
from agents.protocol import CursorStatus
from src.db.models import BaseModel, Vendor
from src.db.repositories import VendorRepository
from src.db.services import SASessionUOW
from src.utils import admin_get_link, simple_slugify
from src.modules.auth.permissions import Permission
from src.services.cursor import CursorClient, CursorError

__all__ = ("VendorAdminView",)
logger = logging.getLogger(__name__)


class VendorAdminForm(Form):
    """Provides extra validation for vendors' creation/updating"""

    slug = StringField(render_kw=RENDER_KW_REQ, label="Slug")
    api_url = URLField(render_kw=RENDER_KW, label="API URL")
    auth_mode = HiddenField(default=VendorMode.API_KEY)
    new_api_key = StringField(render_kw=RENDER_KW, label="New API Key")
    is_active = BooleanField(render_kw={"class": "form-check-input"})


class VendorAdminView(BaseModelView, model=Vendor):
    required_permission = Permission.ADMIN_PANEL
    name = "AI Vendor"
    name_plural = "AI Vendors"
    icon = "fa-solid fa-box-archive"
    list_template = "vendors.html"
    column_list = (Vendor.id, Vendor.slug, Vendor.auth_mode, Vendor.api_url, Vendor.is_active)
    column_formatters = {Vendor.id: lambda model, a: admin_get_link(cast(BaseModel, model))}
    form = VendorAdminForm
    column_details_list = (
        Vendor.id,
        Vendor.slug,
        Vendor.auth_mode,
        Vendor.api_url,
        Vendor.timeout,
        Vendor.is_active,
        Vendor.created_at,
        Vendor.updated_at,
    )
    column_labels = {
        Vendor.slug: "Slug",
        Vendor.api_url: "API URL",
        Vendor.api_key: "Encrypted API Key",
        Vendor.auth_mode: "Authentication mode",
        Vendor.is_active: "Is Active",
    }

    @expose("/cursor-subscription", methods=["GET", "POST"], include_in_schema=False)
    async def cursor_subscription(self, request: Request) -> Response:
        client = CursorClient(get_app_settings())
        if request.method == "GET" and request.query_params.get("status") == "1":
            try:
                return JSONResponse((await client.status()).model_dump())
            except CursorError as exc:
                return JSONResponse(
                    CursorStatus(state="error", error=exc.code).model_dump(), status_code=exc.status
                )

        login_url = None
        error = None
        status_code = 200
        refresh = False
        if request.method == "POST":
            form = await request.form()
            action = form.get("action")
            try:
                if action == "login":
                    login_url = await client.login()
                elif action == "logout":
                    await client.logout()
                elif action == "refresh":
                    refresh = True
                elif action == "save":
                    catalog = await client.models(refresh=True)
                    selected = {str(value) for value in form.getlist("models")}
                    await self._save_subscription_models(catalog, selected)
                elif action == "api_key":
                    await self._use_api_key()
                else:
                    raise HTTPException(status_code=400, detail="Unknown action.")
                if action in {"logout", "save", "api_key"}:
                    return RedirectResponse(
                        request.url_for("admin:view-vendor-cursor_subscription"), status_code=303
                    )
            except CursorError as exc:
                error, status_code = exc.message, exc.status
            except HTTPException as exc:
                error, status_code = str(exc.detail), exc.status_code

        async with SASessionUOW() as uow:
            vendor = await VendorRepository(uow.session).get_by_slug(VendorSlug.CURSOR)
        try:
            status = await client.status()
        except CursorError as exc:
            status = CursorStatus(state="error", error=exc.code)
            error = error or exc.message

        approved = vendor.subscription_models if vendor is not None else []
        catalog = []
        catalog_ready = False
        if status.state == "logged_in":
            try:
                catalog = await client.models(refresh=refresh)
                catalog_ready = True
            except CursorError as exc:
                error = error or exc.message

        response = await self.templates.TemplateResponse(
            request,
            "cursor_subscription.html",
            {
                "vendor": vendor,
                "status": status,
                "login_url": login_url,
                "error": error,
                "catalog": catalog,
                "catalog_ready": catalog_ready,
                "approved": approved,
                "unavailable": sorted(set(approved) - set(catalog)),
            },
            status_code=status_code,
        )
        # Keep the same-origin source on form POSTs so CSRF validation can verify it.
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "same-origin"})
        return response

    @staticmethod
    async def _save_subscription_models(catalog: list[str], selected: set[str]) -> None:
        try:
            async with SASessionUOW() as uow:
                repository = VendorRepository(uow.session)
                vendor = await repository.get_by_slug(VendorSlug.CURSOR)
                approved = vendor.subscription_models if vendor is not None else []
                if not selected.issubset(set(catalog) | set(approved)):
                    raise HTTPException(
                        status_code=400, detail="Refresh the catalog and select models again."
                    )
                models = sorted(selected)
                if vendor is None:
                    await repository.create(
                        {
                            "slug": VendorSlug.CURSOR,
                            "auth_mode": VendorMode.SUBSCRIPTION,
                            "subscription_models": models,
                            "is_active": True,
                        }
                    )
                else:
                    vendor.auth_mode = VendorMode.SUBSCRIPTION
                    vendor.subscription_models = models
                    vendor.is_active = True
        except IntegrityError:
            raise HTTPException(
                status_code=409, detail="Cursor settings changed. Reload and retry."
            ) from None

    @staticmethod
    async def _use_api_key() -> None:
        async with SASessionUOW() as uow:
            vendor = await VendorRepository(uow.session).get_by_slug(VendorSlug.CURSOR)
            if vendor is None or not vendor.api_url or not vendor.api_key:
                raise HTTPException(
                    status_code=400, detail="Set an API URL and key in AI Vendors first."
                )
            vendor.auth_mode = VendorMode.API_KEY

    async def insert_model(self, request: Request, data: FormDataType) -> Any:
        """Creates new vendor entry with API Key's encryption"""

        data = await self._validate(data)
        if new_api_key := data.pop("new_api_key"):
            data["api_key"] = self._encrypt_api_key(str(new_api_key))

        return await super().insert_model(request, data)

    async def update_model(self, request: Request, pk: str, data: FormDataType) -> Any:
        """Updates vendor entry (and encrypt API key if provided)"""

        data = await self._validate(data, vendor_id=int(pk))
        if new_api_key := data.pop("new_api_key"):
            data["api_key"] = self._encrypt_api_key(str(new_api_key))

        return await super().update_model(request, pk, data)

    def _encrypt_api_key(self, plaintext_key: str) -> str:
        """Encrypt API key using application encryption settings"""
        if not plaintext_key:
            raise ValueError("API key cannot be empty")

        settings: AppSettings = get_app_settings()
        try:
            encryption = VendorKeyEncryption(settings.vendor_encryption_key)
            return encryption.encrypt(plaintext_key)

        except Exception as exc:
            raise VendorEncryptionError("Failed to encrypt API key") from exc

    @classmethod
    async def _validate(cls, data: FormDataType, vendor_id: int | None = None) -> FormDataType:
        slug = data.pop("slug", None)
        if not slug:
            raise HTTPException(status_code=400, detail="Slug required")

        validated_slug = await cls._validate_slug(slug=str(slug), vendor_id=vendor_id)
        if validated_slug:
            data["slug"] = validated_slug
        mode = data.get("auth_mode") or VendorMode.API_KEY
        if mode not in (VendorMode.API_KEY, VendorMode.SUBSCRIPTION):
            raise HTTPException(status_code=400, detail="Invalid authentication mode")
        if (
            mode == VendorMode.SUBSCRIPTION
            and (validated_slug or simple_slugify(str(slug))) != VendorSlug.CURSOR
        ):
            raise HTTPException(status_code=400, detail="Subscription is only supported for Cursor")
        if "api_url" in data and not data["api_url"]:
            if mode == VendorMode.API_KEY:
                raise HTTPException(status_code=400, detail="API URL required")
            data["api_url"] = None
        data["auth_mode"] = str(mode)

        data.pop("api_key", None)  # stores already encrypted data and not necessary to provide
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
