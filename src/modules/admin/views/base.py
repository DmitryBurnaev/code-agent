import logging
import datetime

from sqladmin import ModelView

logger = logging.getLogger(__name__)
type FormDataType = dict[str, str | int | datetime.datetime | None]
__all__ = ("BaseModelView",)


class BaseModelView(ModelView):
    can_export = False
    is_async = True
