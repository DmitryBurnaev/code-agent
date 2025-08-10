from typing import Any, TYPE_CHECKING, cast

from jinja2 import FileSystemLoader
from sqladmin import Admin, BaseView, ModelView
from sqladmin.authentication import login_required
from starlette.datastructures import FormData, URL
from starlette.requests import Request
from starlette.responses import Response

from src.modules.admin.auth import AdminAuth
from src.constants import APP_DIR
from src.db.services import SASessionUOW
from src.modules.admin.views import (
    BaseAPPView,
    BaseModelView,
    UserAdminView,
    VendorAdminView,
    AIModelsAdminView,
    TokenAdminView,
)
from src.db.session import get_async_sessionmaker
from src.services.counters import AdminCounter
from src.services.vendors import VendorService
from src.settings import get_app_settings

if TYPE_CHECKING:
    from src.main import CodeAgentAPP
    from src.db.models import BaseModel

ADMIN_VIEWS: tuple[type[BaseView], ...] = (
    UserAdminView,
    VendorAdminView,
    AIModelsAdminView,
    TokenAdminView,
)


class AdminApp(Admin):
    """License-specific admin class."""

    custom_templates_dir = "modules/admin/templates"
    app: "CodeAgentAPP"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._init_jinja_templates()
        self._views: list[BaseModelView | BaseAPPView] = []  # type: ignore
        self._register_views()

    @login_required
    async def index(self, request: Request) -> Response:
        """Index route which can be overridden to create dashboards."""
        settings = get_app_settings()
        async with SASessionUOW() as uow:
            dashboard_stat = await AdminCounter().get_stat(session=uow.session)
            models = await VendorService(settings).get_list_models()

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

    @login_required
    async def create(self, request: Request) -> Response:
        response: Response = await super().create(request)
        if request.method == "GET":
            return response

        # ==== prepare custom logic ====
        identity = request.path_params["identity"]
        model_view: "BaseModelView" = cast("BaseModelView", self._find_model_view(identity))
        if model_view.custom_post_create:
            object_id = int(response.headers["location"])
            response = await model_view.handle_post_create(request, object_id)
        # ====

        return response

    def get_save_redirect_url(
        self,
        request: Request,
        form: FormData,
        model_view: ModelView,
        obj: "BaseModel",
    ) -> str | URL:
        """
        Make more flexable getting redirect URL after saving model instance
        Allows fetching created instance's ID from formed redirect response (location header)
        We have to do this to avoid overriding whole `create` method of this class
        """

        redirect_url: str | URL
        if isinstance(model_view, BaseModelView) and model_view.custom_post_create:
            # required for getting instance ID after base creation's method finished
            redirect_url = str(obj.id)
        else:
            redirect_url = super().get_save_redirect_url(request, form, model_view, obj)

        return redirect_url

    def _init_jinja_templates(self) -> None:
        templates_dir = APP_DIR / self.custom_templates_dir
        self.templates.env.loader.loaders.append(FileSystemLoader(templates_dir))  # type: ignore

    def _register_views(self) -> None:
        for view in ADMIN_VIEWS:
            self.add_view(view)

        for view_instance in self._views:
            view_instance.app = self.app


def make_admin(app: "CodeAgentAPP") -> Admin:
    """Create a simple admin application"""
    return AdminApp(
        app,
        session_maker=get_async_sessionmaker(),
        authentication_backend=AdminAuth(
            secret_key=app.settings.app_secret_key.get_secret_value(),
            settings=app.settings,
        ),
    )
