from sqladmin import expose, BaseView
from starlette.requests import Request
from starlette.responses import Response

from src.services.providers import ProviderService
from src.settings import get_app_settings

__all__ = ("ModelsAdminView",)


class ModelsAdminView(BaseView):
    name = "Models"
    icon = "fa-solid fa-chart-line"

    @expose("/models", methods=["GET"])
    async def get_models(self, request: Request) -> Response:
        settings = get_app_settings()
        models = await ProviderService(settings).get_list_models()

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
