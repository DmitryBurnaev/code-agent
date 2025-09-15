from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.datastructures import FormData, URL
from starlette.requests import Request
from starlette.responses import Response

from src.modules.admin.app import AdminApp, ADMIN_VIEWS, make_admin
from src.modules.admin.views import BaseAPPView, BaseModelView


class TestAdminApp:

    @pytest.fixture
    def mock_app(self) -> MagicMock:
        app = MagicMock()
        app.settings = MagicMock()
        app.settings.admin = MagicMock()
        app.settings.admin.base_url = "/admin"
        app.settings.admin.title = "Test Admin"
        app.settings.app_secret_key = MagicMock()
        app.settings.app_secret_key.get_secret_value.return_value = "test-secret"
        return app

    @pytest.fixture
    def mock_session_factory(self) -> MagicMock:
        session_factory = MagicMock()
        session_factory.class_ = MagicMock()
        session_factory.class_.__mro__ = (MagicMock(), MagicMock())
        return session_factory

    @pytest.fixture
    def admin_app(self, mock_app: MagicMock, mock_session_factory: MagicMock) -> AdminApp:
        with patch("src.modules.admin.app.get_session_factory", return_value=mock_session_factory):
            with patch("sqladmin.helpers.is_async_session_maker", return_value=True):
                return AdminApp(
                    mock_app,
                    base_url="/admin",
                    title="Test Admin",
                    session_maker=mock_session_factory,
                    authentication_backend=AsyncMock(),
                )

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.path_params = {"identity": "test-model"}
        return request

    @pytest.fixture
    def mock_form_data(self) -> FormData:
        return FormData({"field": "value"})

    @pytest.fixture
    def mock_base_model(self) -> MagicMock:
        model = MagicMock()
        model.id = 1
        return model

    @pytest.fixture
    def mock_model_view(self) -> MagicMock:
        view = MagicMock(spec=BaseModelView)
        view.custom_post_create = False
        return view

    @pytest.fixture
    def mock_get_settings(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.app.get_app_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_get_settings.return_value = mock_settings
            yield mock_get_settings

    @pytest.fixture
    def mock_uow_class(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.app.SASessionUOW") as mock_uow_class:
            mock_uow = AsyncMock()
            mock_uow_class.return_value.__aenter__.return_value = mock_uow
            yield mock_uow_class

    @pytest.fixture
    def mock_counter_class(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.app.AdminCounter") as mock_counter_class:
            mock_counter = MagicMock()
            mock_counter.get_stat = AsyncMock()
            mock_counter_class.return_value = mock_counter
            yield mock_counter_class

    @pytest.fixture
    def mock_vendor_service_class(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.app.VendorService") as mock_vendor_service_class:
            mock_vendor_service = MagicMock()
            mock_vendor_service.get_list_models = AsyncMock()
            mock_vendor_service_class.return_value = mock_vendor_service
            yield mock_vendor_service_class

    @pytest.fixture
    def mock_fs_loader_class(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.app.FileSystemLoader") as mock_fs_loader_class:
            mock_fs_loader = MagicMock()
            mock_fs_loader_class.return_value = mock_fs_loader
            yield mock_fs_loader_class

    @pytest.fixture
    def mock_get_error_alert(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.app.get_current_error_alert") as mock_get_error_alert:
            mock_get_error_alert.return_value = "error_alert_func"
            yield mock_get_error_alert

    @pytest.fixture
    def mock_admin_auth_class(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.app.AdminAuth") as mock_admin_auth_class:
            mock_admin_auth = MagicMock()
            mock_admin_auth_class.return_value = mock_admin_auth
            yield mock_admin_auth_class


class TestAdminAppInitialization(TestAdminApp):

    @pytest.fixture
    def mock_session_factory_patch(self) -> Generator[MagicMock, Any, None]:
        with patch("src.modules.admin.app.get_session_factory") as mock_get_session_factory:
            yield mock_get_session_factory

    @pytest.fixture
    def mock_is_async_session_maker(self) -> Generator[MagicMock, Any, None]:
        with patch("sqladmin.helpers.is_async_session_maker", return_value=True) as mock_is_async:
            yield mock_is_async

    def test_admin_app_creation(
        self, 
        mock_app: MagicMock, 
        mock_session_factory: MagicMock,
        mock_session_factory_patch: MagicMock,
        mock_is_async_session_maker: MagicMock,
    ) -> None:
        mock_session_factory_patch.return_value = mock_session_factory
        
        with patch.object(AdminApp, "_init_jinja_templates") as mock_init_jinja:
            with patch.object(AdminApp, "_register_views") as mock_register_views:
                admin = AdminApp(
                    mock_app,
                    base_url="/admin",
                    title="Test Admin",
                    session_maker=mock_session_factory,
                    authentication_backend=MagicMock(),
                )

        assert admin.app == mock_app
        assert admin.custom_templates_dir == "modules/admin/templates"
        assert isinstance(admin._views, list)
        # Verify that initialization methods were called
        mock_init_jinja.assert_called_once()
        mock_register_views.assert_called_once()

    def test_admin_app_real_initialization(
        self, 
        mock_app: MagicMock, 
        mock_session_factory: MagicMock,
        mock_session_factory_patch: MagicMock,
        mock_is_async_session_maker: MagicMock,
        mock_fs_loader_class: MagicMock,
        mock_get_error_alert: MagicMock,
    ) -> None:
        mock_session_factory_patch.return_value = mock_session_factory
        
        admin = AdminApp(
            mock_app,
            base_url="/admin",
            title="Test Admin",
            session_maker=mock_session_factory,
            authentication_backend=MagicMock(),
        )
        # This should call real _init_jinja_templates and _register_views
        assert admin.app == mock_app
        assert admin.custom_templates_dir == "modules/admin/templates"
        assert isinstance(admin._views, list)
        # Verify that templates were initialized
        mock_fs_loader_class.assert_called_once()

    def test_admin_app_initialization_calls(
        self, 
        mock_app: MagicMock, 
        mock_session_factory: MagicMock,
        mock_session_factory_patch: MagicMock,
        mock_is_async_session_maker: MagicMock,
    ) -> None:
        mock_session_factory_patch.return_value = mock_session_factory
        
        with patch.object(AdminApp, "_init_jinja_templates") as mock_init_jinja:
            with patch.object(AdminApp, "_register_views") as mock_register_views:
                AdminApp(
                    mock_app,
                    base_url="/admin",
                    title="Test Admin",
                    session_maker=mock_session_factory,
                    authentication_backend=MagicMock(),
                )

        mock_init_jinja.assert_called_once()
        mock_register_views.assert_called_once()

    def test_admin_app_views_initialization(self, admin_app: AdminApp) -> None:
        assert isinstance(admin_app._views, list)
        # _views contains the registered views from ADMIN_VIEWS
        assert len(admin_app._views) == len(ADMIN_VIEWS)


class TestAdminAppIndex(TestAdminApp):

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

    @pytest.mark.asyncio
    async def test_index_success(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_get_settings: MagicMock,
        mock_uow_class: MagicMock,
        mock_counter_class: MagicMock,
        mock_vendor_service_class: MagicMock,
        mock_dashboard_stat: MagicMock,
        mock_models: list[dict[str, str]],
        mock_template_response: MagicMock,
    ) -> None:
        # Setup mocks
        mock_counter = mock_counter_class.return_value
        mock_counter.get_stat = AsyncMock(return_value=mock_dashboard_stat)

        mock_vendor_service = mock_vendor_service_class.return_value
        mock_vendor_service.get_list_models = AsyncMock(return_value=mock_models)

        # Mock templates
        admin_app.templates = MagicMock()
        admin_app.templates.TemplateResponse = AsyncMock(return_value=mock_template_response)

        # Execute
        result = await admin_app.index(mock_request)

        # Verify
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

    @pytest.mark.asyncio
    async def test_index_vendor_service_error(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_get_settings: MagicMock,
        mock_uow_class: MagicMock,
        mock_counter_class: MagicMock,
        mock_vendor_service_class: MagicMock,
        mock_dashboard_stat: MagicMock,
        mock_template_response: MagicMock,
    ) -> None:
        # Setup mocks
        mock_counter = mock_counter_class.return_value
        mock_counter.get_stat = AsyncMock(return_value=mock_dashboard_stat)

        mock_vendor_service = mock_vendor_service_class.return_value
        mock_vendor_service.get_list_models = AsyncMock(side_effect=Exception("Vendor error"))

        # Mock templates
        admin_app.templates = MagicMock()
        admin_app.templates.TemplateResponse = AsyncMock(return_value=mock_template_response)

        # Execute
        result = await admin_app.index(mock_request)

        # Verify
        assert result == mock_template_response

        # Check that models is empty due to error
        template_call_args = admin_app.templates.TemplateResponse.call_args
        context = template_call_args[1]["context"]
        assert context["models"]["active"] == 0

    @pytest.mark.asyncio
    async def test_index_database_error(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_get_settings: MagicMock,
        mock_uow_class: MagicMock,
        mock_counter_class: MagicMock,
    ) -> None:
        # Setup mocks
        mock_counter = mock_counter_class.return_value
        mock_counter.get_stat = AsyncMock(side_effect=Exception("Database error"))

        # Execute and expect exception
        with pytest.raises(Exception, match="Database error"):
            await admin_app.index(mock_request)


class TestAdminAppCreate(TestAdminApp):

    @pytest.mark.asyncio
    async def test_create_get_request(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_super_create: MagicMock,
    ) -> None:
        # Setup mocks
        mock_request.method = "GET"
        mock_response = MagicMock(spec=Response)
        mock_super_create.return_value = mock_response

        # Execute
        result = await admin_app.create(mock_request)

        # Verify
        assert result == mock_response
        mock_super_create.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_create_post_request_no_custom_post_create(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_model_view: MagicMock,
        mock_super_create: MagicMock,
        mock_find_model_view: MagicMock,
    ) -> None:
        # Setup mocks
        mock_request.method = "POST"
        mock_response = MagicMock(spec=Response)
        mock_model_view.custom_post_create = False
        
        mock_super_create.return_value = mock_response
        mock_find_model_view.return_value = mock_model_view

        # Execute
        result = await admin_app.create(mock_request)

        # Verify
        assert result == mock_response
        mock_super_create.assert_called_once_with(mock_request)

    @pytest.fixture
    def mock_super_create(self) -> Generator[MagicMock, Any, None]:
        with patch.object(AdminApp.__class__.__bases__[0], "create") as mock_super_create:
            yield mock_super_create

    @pytest.fixture
    def mock_find_model_view(self) -> Generator[MagicMock, Any, None]:
        with patch.object(AdminApp, "_find_model_view") as mock_find_model_view:
            yield mock_find_model_view

    @pytest.mark.asyncio
    async def test_create_post_request_with_custom_post_create(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_model_view: MagicMock,
        mock_super_create: MagicMock,
        mock_find_model_view: MagicMock,
    ) -> None:
        # Setup mocks
        mock_request.method = "POST"
        mock_response = MagicMock(spec=Response)
        mock_response.headers = {"location": "123"}
        mock_model_view.custom_post_create = True
        mock_model_view.handle_post_create = AsyncMock(return_value=mock_response)
        
        mock_super_create.return_value = mock_response
        mock_find_model_view.return_value = mock_model_view

        # Execute
        result = await admin_app.create(mock_request)

        # Verify
        assert result == mock_response
        mock_super_create.assert_called_once_with(mock_request)
        mock_model_view.handle_post_create.assert_called_once_with(mock_request, 123)

    @pytest.mark.asyncio
    async def test_create_post_request_handle_post_create_error(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_model_view: MagicMock,
        mock_super_create: MagicMock,
        mock_find_model_view: MagicMock,
    ) -> None:
        # Setup mocks
        mock_request.method = "POST"
        mock_response = MagicMock(spec=Response)
        mock_response.headers = {"location": "123"}
        mock_model_view.custom_post_create = True
        mock_model_view.handle_post_create = AsyncMock(side_effect=Exception("Handle error"))
        
        mock_super_create.return_value = mock_response
        mock_find_model_view.return_value = mock_model_view

        # Execute and expect exception
        with pytest.raises(Exception, match="Handle error"):
            await admin_app.create(mock_request)


class TestAdminAppGetSaveRedirectUrl(TestAdminApp):

    @pytest.fixture
    def mock_super_get_save_redirect_url(self) -> Generator[MagicMock, Any, None]:
        with patch.object(AdminApp.__class__.__bases__[0], "get_save_redirect_url") as mock_super:
            yield mock_super

    def test_get_save_redirect_url_base_model_view_no_custom_post_create(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_form_data: FormData,
        mock_model_view: MagicMock,
        mock_base_model: MagicMock,
        mock_super_get_save_redirect_url: MagicMock,
    ) -> None:
        # Setup mocks
        mock_model_view.custom_post_create = False
        mock_redirect_url = "http://example.com/redirect"
        mock_super_get_save_redirect_url.return_value = mock_redirect_url

        # Execute
        result = admin_app.get_save_redirect_url(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )

        # Verify
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
        # Setup mocks
        mock_model_view.custom_post_create = True
        mock_base_model.id = 123

        # Execute
        result = admin_app.get_save_redirect_url(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )

        # Verify
        assert result == "123"

    def test_get_save_redirect_url_non_base_model_view(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_form_data: FormData,
        mock_base_model: MagicMock,
        mock_super_get_save_redirect_url: MagicMock,
    ) -> None:
        # Setup mocks
        mock_model_view = MagicMock()  # Not a BaseModelView
        mock_redirect_url = "http://example.com/redirect"
        mock_super_get_save_redirect_url.return_value = mock_redirect_url

        # Execute
        result = admin_app.get_save_redirect_url(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )

        # Verify
        assert result == mock_redirect_url
        mock_super_get_save_redirect_url.assert_called_once_with(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )


class TestAdminAppInitJinjaTemplates(TestAdminApp):

    @pytest.fixture
    def mock_app_dir(self) -> Generator[Path, Any, None]:
        with patch("src.modules.admin.app.APP_DIR", Path("/test/app")) as mock_app_dir:
            yield mock_app_dir

    def test_init_jinja_templates(
        self,
        admin_app: AdminApp,
        mock_app_dir: Path,
        mock_fs_loader_class: MagicMock,
        mock_get_error_alert: MagicMock,
    ) -> None:
        # Setup mocks
        admin_app.templates = MagicMock()
        admin_app.templates.env = MagicMock()
        admin_app.templates.env.loader = MagicMock()
        admin_app.templates.env.loader.loaders = []

        # Execute
        admin_app._init_jinja_templates()

        # Verify
        mock_fs_loader_class.assert_called_once_with(Path("/test/app/modules/admin/templates"))
        assert admin_app.templates.env.loader.loaders[0] == mock_fs_loader_class.return_value
        # Check that error_alert was set in globals
        admin_app.templates.env.globals.__setitem__.assert_called_with(
            "error_alert", mock_get_error_alert
        )

    def test_init_jinja_templates_with_existing_loaders(
        self,
        admin_app: AdminApp,
        mock_app_dir: Path,
        mock_fs_loader_class: MagicMock,
        mock_get_error_alert: MagicMock,
    ) -> None:
        # Setup mocks
        existing_loader = MagicMock()
        admin_app.templates = MagicMock()
        admin_app.templates.env = MagicMock()
        admin_app.templates.env.loader = MagicMock()
        admin_app.templates.env.loader.loaders = [existing_loader]

        # Execute
        admin_app._init_jinja_templates()

        # Verify
        assert admin_app.templates.env.loader.loaders[0] == mock_fs_loader_class.return_value
        assert admin_app.templates.env.loader.loaders[1] == existing_loader


class TestAdminAppRegisterViews(TestAdminApp):

    def test_register_views(
        self,
        admin_app: AdminApp,
    ) -> None:
        # Setup mocks
        admin_app.add_view = MagicMock()
        admin_app._views = [MagicMock(spec=BaseAPPView), MagicMock(spec=BaseModelView)]

        # Execute
        admin_app._register_views()

        # Verify
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
        # Setup mocks
        admin_app.add_view = MagicMock()
        custom_view1 = MagicMock(spec=BaseAPPView)
        custom_view2 = MagicMock(spec=BaseModelView)
        admin_app._views = [custom_view1, custom_view2]

        # Execute
        admin_app._register_views()

        # Verify
        assert admin_app.add_view.call_count == len(ADMIN_VIEWS)

        # Check that app is set for custom view instances
        assert custom_view1.app == admin_app.app
        assert custom_view2.app == admin_app.app


class TestMakeAdmin(TestAdminApp):

    def test_make_admin(
        self,
        mock_app: MagicMock,
        mock_session_factory: MagicMock,
        mock_session_factory_patch: MagicMock,
        mock_is_async_session_maker: MagicMock,
        mock_admin_auth_class: MagicMock,
    ) -> None:
        mock_session_factory_patch.return_value = mock_session_factory

        # Execute
        result = make_admin(mock_app)

        # Verify
        assert isinstance(result, AdminApp)
        assert result.app == mock_app
        mock_admin_auth_class.assert_called_once_with(
            secret_key=mock_app.settings.app_secret_key.get_secret_value(),
            settings=mock_app.settings,
        )

    def test_make_admin_with_settings(
        self,
        mock_app: MagicMock,
        mock_session_factory: MagicMock,
        mock_session_factory_patch: MagicMock,
        mock_is_async_session_maker: MagicMock,
        mock_admin_auth_class: MagicMock,
    ) -> None:
        # Setup mocks
        mock_app.settings.admin.base_url = "/custom/admin"
        mock_app.settings.admin.title = "Custom Admin"
        mock_session_factory_patch.return_value = mock_session_factory

        # Execute
        result = make_admin(mock_app)

        # Verify
        assert isinstance(result, AdminApp)
        assert result.app == mock_app


class TestAdminAppEdgeCases(TestAdminApp):

    def test_admin_views_constant(self) -> None:
        assert isinstance(ADMIN_VIEWS, tuple)
        assert len(ADMIN_VIEWS) > 0
        # Check that all views are BaseView subclasses
        for view in ADMIN_VIEWS:
            assert issubclass(view, BaseAPPView) or issubclass(view, BaseModelView)

    def test_admin_app_custom_templates_dir(self, admin_app: AdminApp) -> None:
        assert admin_app.custom_templates_dir == "modules/admin/templates"

    def test_admin_app_app_property(self, admin_app: AdminApp, mock_app: MagicMock) -> None:
        assert admin_app.app == mock_app

    @pytest.mark.asyncio
    async def test_index_template_error(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_get_settings: MagicMock,
        mock_uow_class: MagicMock,
        mock_counter_class: MagicMock,
        mock_vendor_service_class: MagicMock,
        mock_dashboard_stat: MagicMock,
    ) -> None:
        # Setup mocks
        mock_counter = mock_counter_class.return_value
        mock_counter.get_stat = AsyncMock(return_value=mock_dashboard_stat)

        mock_vendor_service = mock_vendor_service_class.return_value
        mock_vendor_service.get_list_models = AsyncMock(return_value=[])

        # Mock templates to raise error
        admin_app.templates = MagicMock()
        admin_app.templates.TemplateResponse = AsyncMock(side_effect=Exception("Template error"))

        # Execute and expect exception
        with pytest.raises(Exception, match="Template error"):
            await admin_app.index(mock_request)

    def test_real_initialization_methods(
        self, 
        mock_app: MagicMock, 
        mock_session_factory: MagicMock,
        mock_session_factory_patch: MagicMock,
        mock_is_async_session_maker: MagicMock,
        mock_fs_loader_class: MagicMock,
        mock_get_error_alert: MagicMock,
    ) -> None:
        mock_session_factory_patch.return_value = mock_session_factory
        
        admin = AdminApp(
            mock_app,
            base_url="/admin",
            title="Test Admin",
            session_maker=mock_session_factory,
            authentication_backend=AsyncMock(),
        )
        # This should call real _init_jinja_templates and _register_views
        assert admin.app == mock_app
        assert admin.custom_templates_dir == "modules/admin/templates"
        assert isinstance(admin._views, list)
        # Verify that templates were initialized
        mock_fs_loader_class.assert_called_once()
        # get_current_error_alert is assigned, not called

    def test_get_save_redirect_url_with_url_object(
        self,
        admin_app: AdminApp,
        mock_request: MagicMock,
        mock_form_data: FormData,
        mock_model_view: MagicMock,
        mock_base_model: MagicMock,
        mock_super_get_save_redirect_url: MagicMock,
    ) -> None:
        # Setup mocks
        mock_model_view.custom_post_create = False
        mock_redirect_url = URL("http://example.com/redirect")
        mock_super_get_save_redirect_url.return_value = mock_redirect_url

        # Execute
        result = admin_app.get_save_redirect_url(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )

        # Verify
        assert result == mock_redirect_url
        mock_super_get_save_redirect_url.assert_called_once_with(
            mock_request, mock_form_data, mock_model_view, mock_base_model
        )
