from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import FormData, URL
from starlette.responses import Response

from src.main import CodeAgentAPP
from src.modules.admin.app import AdminApp, ADMIN_VIEWS, make_admin
from src.modules.admin.views import BaseAPPView, BaseModelView
from src.services.counters import DashboardCounts


@pytest.fixture
def mock_session_factory() -> MagicMock:
    session_factory = MagicMock()
    session_factory.class_ = MagicMock()
    session_factory.class_.__mro__ = (MagicMock(), MagicMock())
    return session_factory


@pytest.fixture
def admin_app(test_app: CodeAgentAPP, mock_session_factory: MagicMock) -> AdminApp:
    with patch("src.modules.admin.app.get_session_factory", return_value=mock_session_factory):
        with patch("sqladmin.helpers.is_async_session_maker", return_value=True):
            return AdminApp(
                test_app,
                base_url="/admin",
                title="Test Admin",
                session_maker=mock_session_factory,
                authentication_backend=AsyncMock(),
            )


@pytest.fixture
def mock_form_data() -> FormData:
    return FormData({"field": "value"})


@pytest.fixture
def mock_base_model() -> MagicMock:
    model = MagicMock()
    model.id = 1
    return model


@pytest.fixture
def mock_model_view() -> MagicMock:
    view = MagicMock(spec=BaseModelView)
    view.custom_post_create = False
    return view


@pytest.fixture
def mock_get_settings() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.admin.app.get_app_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings
        yield mock_get_settings


@pytest.fixture
def mock_uow_class() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.admin.app.SASessionUOW") as mock_uow_class:
        mock_uow = AsyncMock()
        mock_uow_class.return_value.__aenter__.return_value = mock_uow
        yield mock_uow_class


@pytest.fixture
def mock_counter_class() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.admin.app.AdminCounter") as mock_counter_class:
        mock_counter = MagicMock()
        mock_counter.get_stat = AsyncMock()
        mock_counter_class.return_value = mock_counter
        yield mock_counter_class


@pytest.fixture
def mock_vendor_service_class() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.admin.app.VendorService") as mock_vendor_service_class:
        mock_vendor_service = MagicMock()
        mock_vendor_service.get_list_models = AsyncMock()
        mock_vendor_service_class.return_value = mock_vendor_service
        yield mock_vendor_service_class


@pytest.fixture
def mock_super_get_save_redirect_url() -> Generator[MagicMock, Any, None]:
    with patch("sqladmin.application.Admin.get_save_redirect_url") as mock_super:
        yield mock_super


@pytest.fixture
def mock_get_error_alert() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.admin.app.get_current_error_alert") as mock_get_error_alert:
        mock_get_error_alert.return_value = "error_alert_func"
        yield mock_get_error_alert


@pytest.fixture
def mock_admin_auth_class() -> Generator[MagicMock, Any, None]:
    with patch("src.modules.admin.app.AdminAuth") as mock_admin_auth_class:
        mock_admin_auth = MagicMock()
        mock_admin_auth_class.return_value = mock_admin_auth
        yield mock_admin_auth_class


@pytest.fixture(autouse=True)
def mock_is_async_session_maker() -> Generator[MagicMock, Any, None]:
    with patch("sqladmin.helpers.is_async_session_maker", return_value=True) as mock_is_async:
        yield mock_is_async


class TestAdminAppInitialization:

    def test_admin_app_creation(
        self,
        test_app: CodeAgentAPP,
        mock_session_factory: MagicMock,
    ) -> None:
        with patch.object(AdminApp, "_init_jinja_templates") as mock_init_jinja:
            with patch.object(AdminApp, "_register_views") as mock_register_views:
                admin = AdminApp(
                    test_app,
                    base_url="/admin",
                    title="Test Admin",
                    session_maker=mock_session_factory,
                    authentication_backend=MagicMock(),
                )

        assert admin.app == test_app
        assert admin.custom_templates_dir == "modules/admin/templates"
        assert isinstance(admin._views, list)
        mock_init_jinja.assert_called_once()
        mock_register_views.assert_called_once()

    def test_admin_app_views_initialization(self, admin_app: AdminApp) -> None:
        assert isinstance(admin_app._views, list)
        assert len(admin_app._views) == len(ADMIN_VIEWS)


@pytest.mark.asyncio
class TestAdminAppIndex:

    @pytest.fixture
    def mock_dashboard_stat(self) -> MagicMock:
        mock_stat = MagicMock()
        mock_stat.total_vendors = 10
        mock_stat.active_vendors = 8
        return mock_stat

    @pytest.fixture
    def mock_models(self) -> list[dict[str, str]]:
        return [{"name": "model1"}, {"name": "model2"}]

    @pytest.fixture
    def mock_template_response(self) -> MagicMock:
        return MagicMock(spec=Response)

    async def test_index_success(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_counter_class: MagicMock,
        mock_vendor_service_class: MagicMock,
        mock_dashboard_stat: MagicMock,
        mock_models: list[dict[str, str]],
        mock_template_response: MagicMock,
    ) -> None:
        mock_counter = mock_counter_class.return_value
        mock_counter.get_stat = AsyncMock(return_value=mock_dashboard_stat)

        mock_vendor_service = mock_vendor_service_class.return_value
        mock_vendor_service.get_list_models = AsyncMock(return_value=mock_models)

        admin_app.templates = MagicMock()
        admin_app.templates.TemplateResponse = AsyncMock(return_value=mock_template_response)

        result = await admin_app.index(mock_request)

        assert result == mock_template_response
        admin_app.templates.TemplateResponse.assert_called_once()

        # Check template call arguments
        template_call_args = admin_app.templates.TemplateResponse.call_args
        assert template_call_args[0][0] == mock_request
        assert template_call_args[0][1] == "dashboard.html"
        assert "context" in template_call_args[1]

        context = template_call_args[1]["context"]
        assert context["vendors"]["total"] == 10
        assert context["vendors"]["active"] == 8
        assert context["models"]["active"] == 2

    async def test_index_vendor_service_error(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_get_settings: MagicMock,
        mock_counter_class: MagicMock,
        mock_vendor_service_class: MagicMock,
        mock_dashboard_stat: MagicMock,
        mock_template_response: MagicMock,
    ) -> None:
        mock_counter = mock_counter_class.return_value
        mock_counter.get_stat = AsyncMock(return_value=mock_dashboard_stat)

        mock_vendor_service = mock_vendor_service_class.return_value
        mock_vendor_service.get_list_models = AsyncMock(side_effect=Exception("Vendor error"))

        admin_app.templates = MagicMock()
        admin_app.templates.TemplateResponse = AsyncMock(return_value=mock_template_response)

        result = await admin_app.index(mock_request)

        assert result == mock_template_response

        # Check that models is empty due to error
        template_call_args = admin_app.templates.TemplateResponse.call_args
        context = template_call_args[1]["context"]
        assert context["models"]["active"] == 0

    async def test_index_database_error(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_get_settings: MagicMock,
        # mock_uow_class: MagicMock,
        mock_counter_class: MagicMock,
    ) -> None:
        mock_counter = mock_counter_class.return_value
        mock_counter.get_stat = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(Exception, match="Database error"):
            await admin_app.index(mock_request)


@pytest.mark.asyncio
class TestAdminAppCreate:

    async def test_create_get_request(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        mock_request.method = "GET"
        mock_response = MagicMock(spec=Response)
        mock_create.return_value = mock_response

        result = await admin_app.create(mock_request)

        assert result == mock_response
        mock_create.assert_called_once_with(mock_request)

    async def test_create_post_request_no_custom_post_create(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_model_view: MagicMock,
        mock_create: MagicMock,
        mock_find_model_view: MagicMock,
    ) -> None:
        mock_request.method = "POST"
        mock_response = MagicMock(spec=Response)
        mock_model_view.custom_post_create = False

        mock_create.return_value = mock_response
        mock_find_model_view.return_value = mock_model_view

        result = await admin_app.create(mock_request)

        assert result == mock_response
        mock_create.assert_called_once_with(mock_request)

    @pytest.fixture
    def mock_create(self) -> Generator[MagicMock, Any, None]:
        with patch("sqladmin.application.Admin.create") as mock_create:
            yield mock_create

    @pytest.fixture
    def mock_find_model_view(self) -> Generator[MagicMock, Any, None]:
        with patch.object(AdminApp, "_find_model_view") as mock_find_model_view:
            yield mock_find_model_view

    async def test_create_post_request_with_custom_post_create(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_model_view: MagicMock,
        mock_create: MagicMock,
        mock_find_model_view: MagicMock,
    ) -> None:
        mock_request.method = "POST"
        mock_response = MagicMock(spec=Response)
        mock_response.headers = {"location": "123"}
        mock_model_view.custom_post_create = True
        mock_model_view.handle_post_create = AsyncMock(return_value=mock_response)

        mock_create.return_value = mock_response
        mock_find_model_view.return_value = mock_model_view

        result = await admin_app.create(mock_request)

        assert result == mock_response
        mock_create.assert_called_once_with(mock_request)
        mock_model_view.handle_post_create.assert_called_once_with(mock_request, 123)

    @pytest.mark.asyncio
    async def test_create_post_request_handle_post_create_error(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_model_view: MagicMock,
        mock_create: MagicMock,
        mock_find_model_view: MagicMock,
    ) -> None:
        mock_request.method = "POST"
        mock_response = MagicMock(spec=Response)
        mock_response.headers = {"location": "123"}
        mock_model_view.custom_post_create = True
        mock_model_view.handle_post_create = AsyncMock(side_effect=Exception("Handle error"))

        mock_create.return_value = mock_response
        mock_find_model_view.return_value = mock_model_view

        with pytest.raises(Exception, match="Handle error"):
            await admin_app.create(mock_request)


class TestAdminAppGetSaveRedirectUrl:

    def test_get_save_redirect_url_base_model_view_no_custom_post_create(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_form_data: FormData,
        mock_model_view: MagicMock,
        mock_base_model: MagicMock,
        mock_super_get_save_redirect_url: MagicMock,
    ) -> None:
        mock_model_view.custom_post_create = False
        mock_redirect_url = "http://example.com/redirect"
        mock_super_get_save_redirect_url.return_value = mock_redirect_url

        result = admin_app.get_save_redirect_url(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )

        assert result == mock_redirect_url
        mock_super_get_save_redirect_url.assert_called_once_with(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )

    def test_get_save_redirect_url_base_model_view_with_custom_post_create(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_form_data: FormData,
        mock_model_view: MagicMock,
        mock_base_model: MagicMock,
    ) -> None:
        mock_model_view.custom_post_create = True
        mock_base_model.id = 123

        result = admin_app.get_save_redirect_url(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )
        assert result == "123"

    def test_get_save_redirect_url_non_base_model_view(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_form_data: FormData,
        mock_base_model: MagicMock,
        mock_super_get_save_redirect_url: MagicMock,
    ) -> None:
        mock_model_view = MagicMock()  # Not a BaseModelView
        mock_redirect_url = "http://example.com/redirect"
        mock_super_get_save_redirect_url.return_value = mock_redirect_url

        result = admin_app.get_save_redirect_url(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )

        assert result == mock_redirect_url
        mock_super_get_save_redirect_url.assert_called_once_with(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )


class TestAdminAppRegisterViews:

    def test_register_views(
        self,
        admin_app: AdminApp,
    ) -> None:
        admin_app.add_view = MagicMock()
        admin_app._views = [MagicMock(spec=BaseAPPView), MagicMock(spec=BaseModelView)]

        admin_app._register_views()

        assert admin_app.add_view.call_count == len(ADMIN_VIEWS)
        for view in ADMIN_VIEWS:
            admin_app.add_view.assert_any_call(view)

        # Check that app is set for view instances
        for view_instance in admin_app._views:
            assert view_instance.app == admin_app.app

    def test_register_views_with_custom_views(
        self,
        admin_app: AdminApp,
    ) -> None:
        admin_app.add_view = MagicMock()
        custom_view1 = MagicMock(spec=BaseAPPView)
        custom_view2 = MagicMock(spec=BaseModelView)
        admin_app._views = [custom_view1, custom_view2]

        admin_app._register_views()

        assert admin_app.add_view.call_count == len(ADMIN_VIEWS)

        # Check that app is set for custom view instances
        assert custom_view1.app == admin_app.app
        assert custom_view2.app == admin_app.app


class TestMakeAdmin:

    def test_make_admin(
        self,
        test_app: CodeAgentAPP,
        mock_session_factory: MagicMock,
        mock_is_async_session_maker: MagicMock,
        mock_admin_auth_class: MagicMock,
    ) -> None:

        result = make_admin(test_app)

        assert isinstance(result, AdminApp)
        assert result.app == test_app
        mock_admin_auth_class.assert_called_once_with(
            secret_key=test_app.settings.app_secret_key.get_secret_value(),
            settings=test_app.settings,
        )

    def test_make_admin_with_settings(
        self,
        test_app: CodeAgentAPP,
        mock_session_factory: MagicMock,
        mock_is_async_session_maker: MagicMock,
        mock_admin_auth_class: MagicMock,
    ) -> None:
        test_app.settings.admin.base_url = "/custom/admin"
        test_app.settings.admin.title = "Custom Admin"

        result = make_admin(test_app)

        assert isinstance(result, AdminApp)
        assert result.app == test_app


class TestAdminAppEdgeCases:

    def test_admin_views_constant(self) -> None:
        assert isinstance(ADMIN_VIEWS, tuple)
        assert len(ADMIN_VIEWS) > 0
        # Check that all views are BaseView subclasses
        for view in ADMIN_VIEWS:
            assert issubclass(view, BaseAPPView) or issubclass(view, BaseModelView)

    def test_admin_app_custom_templates_dir(self, admin_app: AdminApp) -> None:
        assert admin_app.custom_templates_dir == "modules/admin/templates"

    def test_admin_app_app_property(self, admin_app: AdminApp, test_app: CodeAgentAPP) -> None:
        assert admin_app.app == test_app

    @pytest.mark.asyncio
    async def test_index_template_error(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_get_settings: MagicMock,
        mock_uow_class: MagicMock,
        mock_counter_class: MagicMock,
        mock_vendor_service_class: MagicMock,
    ) -> None:
        mock_counter = mock_counter_class.return_value
        mock_counter.get_stat = AsyncMock(
            return_value=DashboardCounts(
                total_vendors=10,
                active_vendors=2,
            )
        )

        mock_vendor_service = mock_vendor_service_class.return_value
        mock_vendor_service.get_list_models = AsyncMock(return_value=[])

        admin_app.templates = MagicMock()
        admin_app.templates.TemplateResponse = AsyncMock(side_effect=Exception("Template error"))

        with pytest.raises(Exception, match="Template error"):
            await admin_app.index(mock_request)

    def test_real_initialization_methods(
        self,
        test_app: CodeAgentAPP,
        mock_session_factory: MagicMock,
        mock_is_async_session_maker: MagicMock,
        mock_get_error_alert: MagicMock,
    ) -> None:
        admin = AdminApp(
            test_app,
            base_url="/admin",
            title="Test Admin",
            session_maker=mock_session_factory,
            authentication_backend=AsyncMock(),
        )
        # This should call real _init_jinja_templates and _register_views
        assert admin.app == test_app
        assert admin.custom_templates_dir == "modules/admin/templates"
        assert isinstance(admin._views, list)

    def test_get_save_redirect_url_with_url_object(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_form_data: FormData,
        mock_model_view: MagicMock,
        mock_base_model: MagicMock,
        mock_super_get_save_redirect_url: MagicMock,
    ) -> None:
        mock_model_view.custom_post_create = False
        mock_redirect_url = URL("http://example.com/redirect")
        mock_super_get_save_redirect_url.return_value = mock_redirect_url

        result = admin_app.get_save_redirect_url(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )

        assert result == mock_redirect_url
        mock_super_get_save_redirect_url.assert_called_once_with(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )
