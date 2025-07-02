import logging
from typing import cast, Any

from starlette.datastructures import URL
from starlette.requests import Request

from src.modules.auth.tokens import make_token
from src.services.cache import InMemoryCache
from src.utils import admin_get_link
from src.db.models import BaseModel, Token
from src.modules.admin.views.base import BaseModelView, FormDataType

__all__ = ("TokenAdminView",)
logger = logging.getLogger(__name__)


class TokenAdminView(BaseModelView, model=Token):
    icon = "fa-solid fa-key"
    column_list = (Token.id, Token.user, Token.expires_at)
    form_columns = (Token.user, Token.name, Token.expires_at)
    can_edit = False
    column_formatters = {
        Token.id: lambda model, a: admin_get_link(cast(BaseModel, model), target="details")
    }
    column_details_list = (Token.id, Token.user, Token.name, Token.expires_at, Token.created_at)
    column_default_li = ()
    details_template = "token_details.html"

    async def insert_model(self, request: Request, data: FormDataType) -> Token:
        raw_token, hashed_token = make_token()
        data["token"] = hashed_token
        token: Token = await super().insert_model(request, data)
        cache: InMemoryCache = InMemoryCache()
        cache.set(f"token__{token.id}", raw_token)
        return token

    async def get_object_for_details(self, value: Any) -> Token:
        token: Token = await super().get_object_for_details(value)
        cache: InMemoryCache = InMemoryCache()
        cache_key = f"token__{token.id}"
        token.raw_token = str(cache.get(cache_key))
        cache.invalidate(cache_key)
        return token

    def get_save_redirect_url(self, request: Request, token: Token) -> URL:
        """Override get_redirect_url method to return specific URL"""
        return self._build_url_for("admin:details", request=request, obj=token)
