"""Administration view for client configuration."""

from typing import cast

from src.db.models import BaseModel, Client
from src.modules.admin.views.base import BaseModelView
from src.utils import admin_get_link

__all__ = ("ClientAdminView",)


class ClientAdminView(BaseModelView, model=Client):
    """Create and maintain clients available to projects."""

    name = "Client"
    name_plural = "Clients"
    icon = "fa-solid fa-building"
    column_list = (Client.id, Client.name, Client.created_at)
    column_details_list = (Client.id, Client.name, Client.created_at)
    column_formatters = {Client.id: lambda model, _: admin_get_link(cast(BaseModel, model))}
    form_columns = (Client.name,)
