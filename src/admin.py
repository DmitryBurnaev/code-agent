from typing import Any

from sqladmin import ModelView, Admin

from src.db.models import User, Vendor, VendorSettings


class BaseModelView(ModelView):
    admin_app: "AdminApp"


class UserAdmin(BaseModelView, model=User):
    column_list = [User.id, User.login, User.email, User.first_name, User.last_name]


class VendorAdmin(BaseModelView, model=Vendor):
    column_list = [Vendor.id, Vendor.name, Vendor.slug, Vendor.is_active]


class VendorSettingsAdmin(BaseModelView, model=VendorSettings):
    column_list = [VendorSettings.id, VendorSettings.vendor, VendorSettings.model_prefix]


ADMIN_VIEWS: tuple[type[BaseModelView], ...] = (
    UserAdmin,
    VendorAdmin,
    VendorSettingsAdmin,
)


class AdminApp(Admin):
    """License-specific admin class."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._register_views()

    def _register_views(self) -> None:
        for view in ADMIN_VIEWS:
            print(view)
            view.admin_app = self
            self.add_view(view)
