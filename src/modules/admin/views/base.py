import logging
import datetime
from typing import ClassVar

from sqladmin import ModelView
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)
type FormDataType = dict[str, str | int | datetime.datetime | None]
__all__ = ("BaseModelView",)


class BaseModelView(ModelView):
    can_export = False
    is_async = True
    custom_post_create: ClassVar[bool] = False

    async def handle_post_create(self, request: Request, object_id: int) -> Response:
        if not self.custom_post_create:
            raise HTTPException(status_code=400, detail="Missing save details' logic")

        model = await self.get_object_for_details(object_id)
        if not model:
            raise HTTPException(status_code=404, detail="Object not found")

        context = {"model_view": self, "model": model, "title": self.name}

        return await self.templates.TemplateResponse(request, self.details_template, context)
