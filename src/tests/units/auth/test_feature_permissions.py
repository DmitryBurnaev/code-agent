"""Authorization through real API, browser, and admin HTTP entry points."""

from datetime import date
from decimal import Decimal
from typing import Generator
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.responses import JSONResponse, StreamingResponse
from starlette.requests import Request
from starlette.testclient import TestClient

from src.db.models import BaseModel, Token, User, TimeEntry
from src.db.repositories import (
    TokenRepository,
    UserRepository,
    VendorRepository,
    TimeEntryRepository,
)
from src.application import CodeAgentAPP
from src.main import make_app
from src.models import Balance
from src.modules.admin.app import AdminApp, make_admin
from src.modules.admin.auth import AdminAuth
from src.modules.admin.views.base import BaseAPPView, BaseModelView
from sqladmin import BaseView, action, expose
from src.modules.auth.permissions import Permission, has_permission
from src.modules.auth.tokens import GeneratedToken, make_api_token
from src.modules.time_tracker.service import TimeTrackerService
from src.modules.web import views
from src.settings import AppSettings, get_app_settings

API_ROUTES = (
    ("GET", "/api/system/health/", Permission.SYSTEM_API),
    ("GET", "/api/system/info/", Permission.SYSTEM_API),
    ("GET", "/api/ai-proxy/models", Permission.LLM),
    ("POST", "/api/ai-proxy/chat/completions", Permission.LLM),
    ("DELETE", "/api/ai-proxy/chat/completions/example", Permission.LLM),
    ("GET", "/api/billing/balance/", Permission.BILLING),
)
TRACKER_ROUTES = (
    ("GET", "/time-tracker"),
    ("POST", "/time-tracker/timer/start"),
    ("POST", "/time-tracker/timer/stop"),
    ("POST", "/time-tracker/entries"),
    ("POST", "/time-tracker/entries/1"),
    ("POST", "/time-tracker/entries/1/delete"),
)


@pytest.fixture
def user() -> User:
    return User(
        id=7,
        username="agent",
        email="agent@example.test",
        password=User.make_password("secret"),
        is_active=True,
        is_admin=False,
        can_access_admin=False,
        can_access_system_api=False,
        can_use_llm=False,
        can_use_time_tracking=False,
        can_access_billing=False,
    )


@pytest.fixture
def generated_token(app_settings_test: AppSettings) -> GeneratedToken:
    return make_api_token(expires_at=None, settings=app_settings_test)


@pytest.fixture
def api_token(user: User, generated_token: GeneratedToken) -> Token:
    return Token(id=1, user=user, token=generated_token.hashed_value, is_active=True, name="test")


@pytest.fixture
def test_app(
    app_settings_test: AppSettings, user: User, api_token: Token, monkeypatch: pytest.MonkeyPatch
) -> CodeAgentAPP:
    # The HTTP stack and authentication are real; persistence and vendor I/O are isolated.
    factory = async_sessionmaker[AsyncSession]()
    monkeypatch.setattr("src.db.session.get_session_factory", lambda: factory)

    async def find_token(hashed_token: str) -> Token | None:
        return api_token if hashed_token == api_token.token else None

    monkeypatch.setattr(TokenRepository, "get_by_token", AsyncMock(side_effect=find_token))
    monkeypatch.setattr(UserRepository, "get_by_username", AsyncMock(return_value=user))
    monkeypatch.setattr(UserRepository, "first", AsyncMock(return_value=user))
    monkeypatch.setattr(VendorRepository, "all", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "src.services.vendors.VendorService.get_list_models", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "src.services.proxy.ProxyService.handle_request",
        AsyncMock(return_value=JSONResponse({"ok": True})),
    )
    monkeypatch.setattr(
        "src.services.balances.SelectelBalanceProvider.get_balance",
        AsyncMock(return_value=Balance(balance=Decimal("12.34"), currency="RUB")),
    )
    monkeypatch.setattr(
        views,
        "dashboard_time_summary",
        AsyncMock(return_value=views.DashboardTimeSummary(date(2026, 10, 26), 0, 0, None, 0)),
    )
    monkeypatch.setattr(
        views,
        "time_tracker_context",
        AsyncMock(
            return_value={
                "calendar_events": [],
                "entries": [],
                "recent_entries": [],
                "active_entry": None,
                "today_total_duration": "0m",
                "calendar_date": "2026-10-28",
                "calendar_view": "week",
            }
        ),
    )
    app = make_app(app_settings_test)
    app.dependency_overrides[get_app_settings] = lambda: app_settings_test
    app.state.test_admin = make_admin(app)
    return app


@pytest.fixture
def permission_client(
    test_app: CodeAgentAPP, generated_token: GeneratedToken
) -> Generator[TestClient, None]:
    # No lifespan: unbound sessions are enough for mocked repository operations.
    client = TestClient(
        test_app,
        base_url="https://testserver",
        headers={"Authorization": f"Bearer {generated_token.value}"},
    )
    try:
        yield client
    finally:
        client.close()


@pytest.mark.parametrize("permission", list(Permission))
def test_permissions_are_independent_and_superuser_overrides(
    user: User, permission: Permission
) -> None:
    assert not has_permission(user, permission)
    setattr(user, permission.value, True)
    for candidate in Permission:
        assert has_permission(user, candidate) is (candidate == permission)
    setattr(user, permission.value, False)
    user.is_admin = True
    assert all(has_permission(user, candidate) for candidate in Permission)
    user.is_active = False
    assert not any(has_permission(user, candidate) for candidate in Permission)


@pytest.mark.parametrize("method,path,required", API_ROUTES)
@pytest.mark.parametrize("granted", [None, *Permission])
def test_api_permission_matrix(
    permission_client: TestClient,
    user: User,
    method: str,
    path: str,
    required: Permission,
    granted: Permission | None,
) -> None:
    if granted is not None:
        setattr(user, granted.value, True)
    response = permission_client.request(method, path, json={"model": "example", "messages": []})
    assert response.status_code == (200 if granted == required else 403)


@pytest.mark.parametrize("method,path,required", API_ROUTES)
def test_superuser_has_all_api_permissions(
    permission_client: TestClient, user: User, method: str, path: str, required: Permission
) -> None:
    user.is_admin = True
    assert (
        permission_client.request(
            method, path, json={"model": "example", "messages": []}
        ).status_code
        == 200
    )


def test_token_permissions_are_reloaded_on_each_request(
    permission_client: TestClient, user: User
) -> None:
    user.can_access_system_api = True
    assert permission_client.get("/api/system/health/").status_code == 200
    user.can_access_system_api = False
    assert permission_client.get("/api/system/health/").status_code == 403
    user.is_admin = True
    assert permission_client.get("/api/system/health/").status_code == 200
    user.is_admin = False
    assert permission_client.get("/api/system/health/").status_code == 403


@pytest.mark.parametrize("inactive", ["user", "token"])
def test_inactive_superuser_or_token_still_gets_401(
    permission_client: TestClient, user: User, api_token: Token, inactive: str
) -> None:
    user.is_admin = True
    if inactive == "user":
        user.is_active = False
    else:
        api_token.is_active = False
    assert permission_client.get("/api/system/health/").status_code == 401


@pytest.mark.parametrize("authorization", ["", "invalid-token"])
def test_api_authentication_failure_remains_401(
    permission_client: TestClient, authorization: str
) -> None:
    assert (
        permission_client.get(
            "/api/system/health/", headers={"Authorization": authorization}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("path", ["/api/ai-proxy/models", "/api/ai-proxy/chat/completions"])
def test_preflight_needs_no_authentication_or_permission(
    permission_client: TestClient, path: str
) -> None:
    response = permission_client.options(path, headers={"Authorization": ""})
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "*"


def test_llm_permission_covers_streaming(
    permission_client: TestClient, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    user.can_use_llm = True
    handler = AsyncMock(
        return_value=StreamingResponse(iter(["data: example\n\n"]), media_type="text/event-stream")
    )
    monkeypatch.setattr("src.services.proxy.ProxyService.handle_request", handler)
    payload = {"model": "example", "messages": [], "stream": True}
    assert (
        permission_client.post("/api/ai-proxy/chat/completions", json=payload).text
        == "data: example\n\n"
    )
    user.can_use_llm = False
    assert permission_client.post("/api/ai-proxy/chat/completions", json=payload).status_code == 403
    handler.assert_awaited_once()


@pytest.mark.parametrize("method,path", TRACKER_ROUTES)
def test_tracker_rejects_direct_requests_before_data_access(
    permission_client: TestClient, method: str, path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = AsyncMock()
    monkeypatch.setattr(views, "TimeTrackerService", tracker)
    permission_client.post("/login", data={"username": "agent", "password": "secret"})
    assert permission_client.request(method, path).status_code == 403
    tracker.assert_not_called()


@pytest.mark.parametrize("method,path", TRACKER_ROUTES[1:])
@pytest.mark.parametrize("superuser", [False, True])
def test_tracker_mutations_allow_permission_or_superuser(
    permission_client: TestClient,
    user: User,
    method: str,
    path: str,
    superuser: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.is_admin = superuser
    user.can_use_time_tracking = not superuser
    permission_client.post(
        "/login", data={"username": "agent", "password": "secret"}, follow_redirects=False
    )
    entry = TimeEntry(id=1, user_id=user.id, project="Example", task="Work")
    lookup = AsyncMock(return_value=entry)
    monkeypatch.setattr(TimeEntryRepository, "get_for_user", lookup)
    operations = {}
    for name in ("start_timer", "stop_timer", "create_entry", "update_entry"):
        operation = AsyncMock(return_value=entry)
        monkeypatch.setattr(TimeTrackerService, name, operation)
        operations[name] = operation
    deleted = AsyncMock()
    monkeypatch.setattr(TimeEntryRepository, "delete", deleted)
    response = permission_client.request(
        method,
        path,
        data={
            "project": "1",
            "task": "Work",
            "started_at": "2026-10-28T10:00",
            "ended_at": "2026-10-28T11:00",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    if path.endswith("/delete"):
        lookup.assert_awaited_once_with(1, user.id)
        deleted.assert_awaited_once_with(entry)
    elif path.endswith("/1"):
        lookup.assert_awaited_once_with(1, user.id)
        call = operations["update_entry"].await_args
        assert call is not None
        assert call.args[0] is entry
    else:
        name = (
            "start_timer"
            if path.endswith("/start")
            else "stop_timer" if path.endswith("/stop") else "create_entry"
        )
        call = operations[name].await_args
        assert call is not None
        assert call.args[0] == user.id


@pytest.mark.parametrize("path", ["/time-tracker/entries/1", "/time-tracker/entries/1/delete"])
@pytest.mark.parametrize("superuser", [False, True])
def test_tracker_preserves_ownership_for_all_users(
    permission_client: TestClient,
    user: User,
    path: str,
    superuser: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.is_admin = superuser
    user.can_use_time_tracking = not superuser
    permission_client.post(
        "/login", data={"username": "agent", "password": "secret"}, follow_redirects=False
    )
    lookup = AsyncMock(return_value=None)
    update, delete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(TimeEntryRepository, "get_for_user", lookup)
    monkeypatch.setattr(TimeEntryRepository, "delete", delete)
    monkeypatch.setattr(TimeTrackerService, "update_entry", update)
    response = permission_client.post(
        path, data={"started_at": "2026-10-28T10:00"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "not+found" in response.headers["location"]
    lookup.assert_awaited_once_with(1, user.id)
    update.assert_not_awaited()
    delete.assert_not_awaited()


@pytest.mark.parametrize("superuser", [False, True])
def test_web_permissions_and_widgets_change_with_existing_session(
    permission_client: TestClient,
    user: User,
    superuser: bool,
) -> None:
    assert (
        permission_client.post(
            "/login", data={"username": "agent", "password": "secret"}
        ).status_code
        == 200
    )
    assert permission_client.get("/").status_code == 200
    assert permission_client.get("/time-tracker").status_code == 403
    if superuser:
        user.is_admin = True
    else:
        user.can_use_time_tracking = True
        user.can_access_billing = True
    response = permission_client.get("/")
    assert 'href="/time-tracker"' in response.text
    assert "Tracked this week" in response.text
    assert "12.34 RUB" in response.text
    assert permission_client.get("/time-tracker").status_code == 200
    user.is_admin = False
    user.can_use_time_tracking = False
    user.can_access_billing = False
    response = permission_client.get("/")
    assert response.status_code == 200
    assert 'href="/time-tracker"' not in response.text
    assert "Tracked this week" not in response.text
    assert "Selectel balance" not in response.text
    assert permission_client.get("/time-tracker").status_code == 403


@pytest.mark.parametrize(
    "tracking,billing", [(False, False), (True, False), (False, True), (True, True)]
)
def test_dashboard_does_not_fetch_or_render_restricted_data(
    permission_client: TestClient,
    user: User,
    tracking: bool,
    billing: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user.can_use_time_tracking = tracking
    user.can_access_billing = billing
    summary = AsyncMock(return_value=views.DashboardTimeSummary(date(2026, 10, 26), 0, 0, None, 0))
    balance = AsyncMock(return_value=Balance(balance=Decimal("12.34"), currency="RUB"))
    monkeypatch.setattr(views, "dashboard_time_summary", summary)
    monkeypatch.setattr(views, "dashboard_balance", balance)
    permission_client.post(
        "/login", data={"username": "agent", "password": "secret"}, follow_redirects=False
    )
    response = permission_client.get("/")
    assert response.status_code == 200
    assert ("Tracked this week" in response.text) is tracking
    assert ("Selectel balance" in response.text) is billing
    assert (summary.await_count == 1) is tracking
    assert (balance.await_count == 1) is billing


@pytest.mark.parametrize("superuser", [False, True])
def test_admin_login_and_session_recheck_permissions(
    permission_client: TestClient,
    user: User,
    test_app: CodeAgentAPP,
    superuser: bool,
) -> None:
    base = test_app.settings.admin.base_url
    credentials = {"username": "agent", "password": "secret"}
    assert (
        permission_client.post(
            base + "/login", data=credentials, follow_redirects=False
        ).status_code
        == 400
    )
    user.is_admin = superuser
    user.can_access_admin = not superuser
    assert (
        permission_client.post(
            base + "/login", data=credentials, follow_redirects=False
        ).status_code
        == 302
    )
    response = permission_client.get(base + "/user/create")
    assert response.status_code == 200
    assert "Is Admin (all rights)" in response.text
    for permission in Permission:
        assert f'name="{permission.value}"' in response.text
    assert permission_client.get("/api/system/health/").status_code == (200 if superuser else 403)
    user.is_admin = False
    user.can_access_admin = False
    assert permission_client.get(base + "/user/create", follow_redirects=False).status_code == 302


def test_inactive_user_loses_web_and_admin_sessions(
    permission_client: TestClient,
    user: User,
    test_app: CodeAgentAPP,
) -> None:
    user.is_admin = True
    credentials = {"username": "agent", "password": "secret"}
    permission_client.post("/login", data=credentials, follow_redirects=False)
    base = test_app.settings.admin.base_url
    permission_client.post(base + "/login", data=credentials, follow_redirects=False)
    user.is_active = False
    assert permission_client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert permission_client.get(base + "/user/create", follow_redirects=False).status_code == 302


class ExampleBillingView(BaseAPPView):
    required_permission = Permission.BILLING
    name = "Example Billing Feature"

    @expose("/example-billing", methods=["GET", "POST"])
    async def billing(self, request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})


class AuthorizationTestBase(DeclarativeBase):
    pass


class AuthorizationProbe(AuthorizationTestBase):
    __tablename__ = "authorization_probe"
    id: Mapped[int] = mapped_column(primary_key=True)


class ExampleBillingModelView(BaseModelView, model=AuthorizationProbe):
    required_permission = Permission.BILLING

    @action("probe")
    async def probe(self, request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})


def test_sqladmin_enforces_feature_grants_for_crud_and_custom_actions(
    permission_client: TestClient,
    user: User,
    test_app: CodeAgentAPP,
) -> None:
    admin: AdminApp = test_app.state.test_admin
    admin.add_view(ExampleBillingModelView)
    base = f"{test_app.settings.admin.base_url}/{ExampleBillingModelView.identity}"
    user.can_access_admin = True
    permission_client.post(
        test_app.settings.admin.base_url + "/login",
        data={"username": "agent", "password": "secret"},
        follow_redirects=False,
    )
    for method, path in (
        ("GET", "/list"),
        ("GET", "/details/1"),
        ("GET", "/create"),
        ("POST", "/create"),
        ("GET", "/edit/1"),
        ("POST", "/edit/1"),
        ("DELETE", "/delete?pks=1"),
        ("GET", "/action/probe"),
    ):
        assert permission_client.request(method, base + path).status_code == 403
    user.can_access_billing = True
    assert permission_client.get(base + "/create").status_code == 200
    assert permission_client.get(base + "/action/probe").status_code == 200
    user.can_access_billing = False
    assert permission_client.get(base + "/action/probe").status_code == 403
    user.is_admin = True
    assert permission_client.get(base + "/action/probe").status_code == 200


def test_feature_admin_views_require_panel_and_feature_access(
    permission_client: TestClient,
    user: User,
    test_app: CodeAgentAPP,
) -> None:
    admin: AdminApp = test_app.state.test_admin
    admin.add_view(ExampleBillingView)
    base = test_app.settings.admin.base_url
    user.can_access_admin = True
    permission_client.post(
        base + "/login", data={"username": "agent", "password": "secret"}, follow_redirects=False
    )
    for method in ("GET", "POST"):
        assert permission_client.request(method, base + "/example-billing").status_code == 403
    assert ExampleBillingView.name not in permission_client.get(base + "/user/create").text
    user.can_access_billing = True
    assert permission_client.get(base + "/example-billing").status_code == 200
    assert ExampleBillingView.name in permission_client.get(base + "/user/create").text
    user.can_access_billing = False
    assert permission_client.post(base + "/example-billing").status_code == 403
    user.is_admin = True
    assert permission_client.post(base + "/example-billing").status_code == 200
    user.is_admin = False
    user.can_access_admin = False
    user.can_access_billing = True
    assert (
        permission_client.get(base + "/example-billing", follow_redirects=False).status_code == 302
    )


def test_admin_registration_rejects_views_without_explicit_shared_policy(
    test_app: CodeAgentAPP,
) -> None:
    admin: AdminApp = test_app.state.test_admin

    class MissingPermission(BaseAPPView):
        pass

    class UncheckedView(BaseView):
        pass

    with pytest.raises(ValueError, match="required_permission"):
        admin.add_view(MissingPermission)
    with pytest.raises(ValueError, match="required_permission"):
        admin.add_base_view(MissingPermission)
    with pytest.raises(ValueError, match="shared access-controlled base"):
        admin.add_view(UncheckedView)
    with pytest.raises(ValueError, match="shared access-controlled base"):
        admin.add_base_view(UncheckedView)


@pytest.mark.parametrize("permission", list(Permission))
def test_admin_form_persists_each_permission_independently(
    test_app: CodeAgentAPP,
    permission_client: TestClient,
    user: User,
    permission: Permission,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    BaseModel.metadata.create_all(engine)
    factory = sessionmaker(engine)
    backend = AdminAuth(test_app.settings.app_secret_key.get_secret_value(), test_app.settings)
    AdminApp(
        test_app, base_url="/test-admin", session_maker=factory, authentication_backend=backend
    )
    user.can_access_admin = True
    monkeypatch.setattr(UserRepository, "get_by_username", AsyncMock(return_value=user))
    assert (
        permission_client.post(
            "/test-admin/login",
            data={"username": "agent", "password": "secret"},
            follow_redirects=False,
        ).status_code
        == 302
    )
    monkeypatch.setattr(UserRepository, "get_by_username", AsyncMock(return_value=None))
    data = {
        "username": "new-user",
        "email": "new@example.test",
        "new_password": "new-secret",
        "repeat_password": "new-secret",
        "is_active": "y",
        permission.value: "y",
        "save": "Save",
    }
    try:
        response = permission_client.post(
            "/test-admin/user/create", data=data, follow_redirects=False
        )
        assert response.status_code == 302, response.text
        with Session(engine) as session:
            created: User = session.scalars(sa.select(User)).one()
            assert created.is_admin is False
            assert created.verify_password("new-secret")
            assert all(getattr(created, p.value) is (p == permission) for p in Permission)
            pk = created.id
        edit = permission_client.get(f"/test-admin/user/edit/{pk}")
        assert edit.status_code == 200
        # Saving without the checkbox must revoke its stored value.
        response = permission_client.post(
            f"/test-admin/user/edit/{pk}",
            data={"email": "new@example.test", "is_active": "y", "save": "Save"},
            follow_redirects=False,
        )
        assert response.status_code == 302, response.text
        with Session(engine) as session:
            updated = session.get(User, pk)
            assert updated is not None
            assert not any(getattr(updated, p.value) for p in Permission)
            assert updated.verify_password("new-secret")
    finally:
        engine.dispose()
