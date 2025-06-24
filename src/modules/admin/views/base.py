import logging

from sqladmin import ModelView

logger = logging.getLogger(__name__)
type FormDataType = dict[str, str | int | None]


class BaseModelView(ModelView):
    can_export = False
    is_async = True
