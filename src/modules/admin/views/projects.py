"""Administration view for project configuration."""

from typing import cast

from src.db.models import BaseModel, Project
from src.modules.admin.views.base import BaseModelView
from src.utils import admin_get_link

__all__ = ("ProjectAdminView",)


class ProjectAdminView(BaseModelView, model=Project):
    """Create projects and associate each project with an optional client."""

    name = "Project"
    name_plural = "Projects"
    icon = "fa-solid fa-folder-tree"
    column_list = (Project.id, Project.name, Project.client, Project.created_at)
    column_details_list = (Project.id, Project.name, Project.client, Project.created_at)
    column_formatters = {Project.id: lambda model, _: admin_get_link(cast(BaseModel, model))}
    form_columns = (Project.name, Project.client)
