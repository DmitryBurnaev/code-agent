import logging
from typing import cast, Any

from starlette.requests import Request

from src.modules.auth.tokens import make_token
from src.utils import admin_get_link
from src.db.models import BaseModel, Token
from src.modules.admin.views.base import BaseModelView, FormDataType

__all__ = ("TokenAdmin",)
logger = logging.getLogger(__name__)


class TokenAdmin(BaseModelView, model=Token):
    icon = "fa-solid fa-key"
    column_list = (Token.id, Token.user, Token.expires_at)
    column_details_list = (
        Token.id,
        Token.token,
        Token.user,
        Token.expires_at,
        Token.created_at,
        Token.updated_at,
    )
    column_formatters = {Token.id: lambda model, a: admin_get_link(cast(BaseModel, model))}

    async def insert_model(self, request: Request, data: FormDataType) -> Any:
        raw_token, hashed_token = make_token()
        data["token"] = hashed_token
        # TODO: provide raw_token to the context (show user on the result admin view)
        return await super().insert_model(request, data)
