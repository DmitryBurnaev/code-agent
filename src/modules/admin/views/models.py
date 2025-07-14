from sqladmin import expose
from starlette.requests import Request
from starlette.responses import Response

from src.modules.admin.views.base import BaseAPPView
from src.services.vendors import VendorService
from src.settings import get_app_settings

__all__ = ("ModelsAdminView",)


class ModelsAdminView(BaseAPPView):
    name = "Models"
    icon = "fa-solid fa-chart-line"

    @expose("/models", methods=["GET"])
    async def get_models(self, request: Request) -> Response:
        settings = get_app_settings()
        models = await VendorService(settings).get_list_models()

        context = {
            "vendor_models": [
                {"vendor": model.vendor, "model": model.id, "original_model": model.vendor_id}
                for model in models
            ],
        }
        return await self.templates.TemplateResponse(
            request,
            name="models.html",
            context=context,
        )
