from typing import Any

from jinja2 import FileSystemLoader
from sqladmin import Admin
from sqladmin.authentication import login_required
from starlette.requests import Request
from starlette.responses import Response

from src.constants import APP_DIR
from src.routers.admin import BaseModelView, UserAdmin, VendorAdmin
from src.services.counters import AdminCounter

ADMIN_VIEWS: tuple[type[BaseModelView], ...] = (
    UserAdmin,
    VendorAdmin,
    VendorSettingsAdmin,
)


class AdminApp(Admin):
    """License-specific admin class."""

    custom_templates_dir = "templates/admin"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._register_views()
        self._init_jinja_templates()

    @login_required
    async def index(self, request: Request) -> Response:
        """Index route which can be overridden to create dashboards."""
        dashboard_stat = await AdminCounter().get_stat()

        context = {
            "vendors": {
                "total": dashboard_stat.total_vendors,
                "active": dashboard_stat.active_vendors,
            }
        }
        return await self.templates.TemplateResponse(request, "dashboard.html", context=context)

    def _init_jinja_templates(self) -> None:
        templates_dir = APP_DIR / self.custom_templates_dir
        self.templates.env.loader.loaders.append(FileSystemLoader(templates_dir))  # type: ignore

    def _register_views(self) -> None:
        for view in ADMIN_VIEWS:
            self.add_view(view)
