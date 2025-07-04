import logging
import datetime
from typing import ClassVar

from sqladmin import ModelView

logger = logging.getLogger(__name__)
type FormDataType = dict[str, str | int | datetime.datetime | None]
__all__ = ("BaseModelView",)


class BaseModelView(ModelView):
    can_export = False
    is_async = True
    save_redirect: ClassVar[str | None] = None
    # get_save_redirect_url: Callable | None = None
    #
    # def get_redirect_url(self, request: Request, obj: Any) -> URL | None:
    #     """Override get_redirect_url method to return specific URL"""
    #     if self.save_redirect is not None:
    #         identity = request.path_params["identity"]
    #         return request.url_for(self.save_redirect, identity=identity, identifier=obj.id)
    #
    #     return None
