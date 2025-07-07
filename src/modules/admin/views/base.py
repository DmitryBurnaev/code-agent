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
