import logging
import datetime
from typing import cast

from sqladmin import action
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse

from src.db.repositories import TokenRepository
from src.db.services import SASessionUOW
from src.db.models import BaseModel, Token
from src.services.cache import InMemoryCache
from src.utils import admin_get_link
from src.modules.auth.tokens import make_api_token
from src.modules.admin.views.base import BaseModelView, FormDataType

__all__ = ("TokenAdminView",)
logger = logging.getLogger(__name__)


class TokenAdminView(BaseModelView, model=Token):
    name = "API Token"
    name_plural = "API Tokens"
    icon = "fa-solid fa-key"
    column_list = (Token.id, Token.user, Token.is_active, Token.expires_at)
    form_columns = (Token.user, Token.name, Token.expires_at)
    can_edit = False
    column_formatters = {
        Token.id: lambda model, a: admin_get_link(cast(BaseModel, model), target="details")
    }
    column_details_list = (
        Token.id,
        Token.user,
        Token.name,
        Token.is_active,
        Token.expires_at,
        Token.created_at,
    )
    column_default_li = ()
    details_template = "token_details.html"
    custom_post_create = True

    async def insert_model(self, request: Request, data: FormDataType) -> Token:
        """
        Create a new token and save it to the database with generated token and its hashed value
        """
        expires_at: datetime.datetime | None = None
        if data.get("expires_at"):
            expires_at = cast(datetime.datetime, data["expires_at"])

        token_info = make_api_token(expires_at=expires_at, settings=self.app.settings)
        data["token"] = token_info.hashed_value
        token: Token = await super().insert_model(request, data)
        cache = InMemoryCache()
        cache.set(f"token__{token.id}", token_info.value, ttl=10)  # 10 seconds for showing to user
        return token

    async def get_object_for_details(self, request: Request) -> Token:
        """
        Get token object and show it in the details page.
        """
        token: Token = await super().get_object_for_details(request)
        cache: InMemoryCache = InMemoryCache()
        cache_key = f"token__{token.id}"
        token.raw_token = str(cache.get(cache_key))
        cache.invalidate(cache_key)
        return token

    def get_save_redirect_url(self, request: Request, token: Token) -> URL:
        """Override get_redirect_url method to return specific URL"""
        return self._build_url_for("admin:details", request=request, obj=token)

    @action(
        name="deactivate",
        label="Deactivate",
        add_in_detail=True,
        add_in_list=True,
        confirmation_message="Are you sure you want to deactivate selected tokens?",
    )
    async def deactivate_tokens(self, request: Request) -> Response:
        """Downloads single license (as single *.lic file) and several (combined to *.zip)"""

        return await self._set_active(request, is_active=False)

    @action(
        name="activate",
        label="Activate",
        add_in_detail=True,
        add_in_list=True,
        confirmation_message="Are you sure you want to activate selected tokens?",
    )
    async def activate_tokens(self, request: Request) -> Response:
        """Activate tokens by their IDs"""
        return await self._set_active(request, is_active=True)

    async def _set_active(self, request: Request, is_active: bool) -> Response:
        """Set active status for tokens by their IDs"""

        token_ids = request.query_params.get("pks", "").split(",")
        if not token_ids:
            raise RuntimeError("No pks provided")

        logger.info(
            "[ADMIN] %s tokens: %r", "Deactivating" if not is_active else "Activating", token_ids
        )
        async with SASessionUOW() as uow:
            await TokenRepository(session=uow.session).set_active(token_ids, is_active=is_active)
            await uow.commit()

        return RedirectResponse(url=request.url_for("admin:list", identity=self.identity))
