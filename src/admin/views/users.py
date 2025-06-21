import logging
from typing import cast, Any, Mapping, Sequence

from fastapi import HTTPException
from starlette.requests import Request
from wtforms import Form, StringField, EmailField, PasswordField, BooleanField

from src.admin.views.base import BaseModelView, FormDataType
from src.constants import RENDER_KW
from src.db.models import BaseModel, User
from src.utils import admin_get_link

__all__ = ("UserAdmin",)
logger = logging.getLogger(__name__)


class UserAdminForm(Form):
    """Provides extra validation for users' creation/updating"""

    username = StringField(render_kw=RENDER_KW, label="Username")
    email = EmailField(render_kw=RENDER_KW)
    new_password = PasswordField(render_kw={"class": "form-control"}, label="New Password")
    repeat_password = PasswordField(
        render_kw={"class": "form-control"},
        label="Repeat New Password",
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
