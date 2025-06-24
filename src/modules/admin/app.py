from typing import Any, TYPE_CHECKING

from jinja2 import FileSystemLoader
from sqladmin import Admin, BaseView
from sqladmin.authentication import login_required
from starlette.requests import Request
from starlette.responses import Response

from src.modules.admin.auth import AdminAuth
from src.constants import APP_DIR
from src.db.services import SASessionUOW
from src.modules.admin.views import UserAdmin, VendorAdmin, ModelsAdmin, TokenAdmin
from src.db.session import get_async_sessionmaker
from src.services.counters import AdminCounter
from src.services.providers import ProviderService
from src.settings import get_app_settings

if TYPE_CHECKING:
    from src.main import CodeAgentAPP

ADMIN_VIEWS: tuple[type[BaseView], ...] = (
    UserAdmin,
    VendorAdmin,
    ModelsAdmin,
    TokenAdmin,
)


class AdminApp(Admin):
    """License-specific admin class."""

    custom_templates_dir = "admin/templates"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._init_jinja_templates()
        self._register_views()

    @login_required
    async def index(self, request: Request) -> Response:
        """Index route which can be overridden to create dashboards."""
        settings = get_app_settings()
        async with SASessionUOW() as uow:
            dashboard_stat = await AdminCounter().get_stat(session=uow.session)
            models = await ProviderService(settings).get_list_models()

        context = {
            "vendors": {
                "total": dashboard_stat.total_vendors,
                "active": dashboard_stat.active_vendors,
            },
            "models": {
                "active": len(models),
            },
        }
        return await self.templates.TemplateResponse(request, "dashboard.html", context=context)

    def _init_jinja_templates(self) -> None:
        templates_dir = APP_DIR / self.custom_templates_dir
        self.templates.env.loader.loaders.append(FileSystemLoader(templates_dir))  # type: ignore

    def _register_views(self) -> None:
        for view in ADMIN_VIEWS:
            self.add_view(view)


def make_admin(app: "CodeAgentAPP") -> Admin:
    return AdminApp(
        app,
        session_maker=get_async_sessionmaker(),
        authentication_backend=AdminAuth(secret_key=app.settings.secret_key.get_secret_value()),
    )
