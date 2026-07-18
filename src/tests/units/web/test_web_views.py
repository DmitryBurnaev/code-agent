from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from src.main import CodeAgentAPP
from src.modules.web import views
from src.tests.mocks import MockUser


@pytest.fixture
def web_client(test_app: CodeAgentAPP) -> TestClient:
    with TestClient(test_app, base_url="https://testserver") as client:
        yield client


@pytest.fixture
def active_user() -> MockUser:
    return MockUser(id=3, is_active=True, username="agent")


def test_app_registers_web_routes_static_files_and_isolated_session(
    test_app: CodeAgentAPP,
) -> None:
    web_route_paths = {route.path for route in views.router.routes}
    assert {"/", "/login", "/logout", "/time-tracker"} <= web_route_paths
    assert any(getattr(route, "path", None) == "/static" for route in test_app.routes)

    middleware = next(
        middleware
        for middleware in test_app.user_middleware
        if middleware.cls.__name__ == "SessionMiddleware"
    )
    assert middleware.kwargs["session_cookie"] == "code_agent_web_session"
    assert middleware.kwargs["session_cookie"] != "session"
    assert middleware.kwargs["max_age"] == 2 * 24 * 3600
    assert middleware.kwargs["https_only"] is True


def test_login_page_and_static_assets_render(web_client: TestClient) -> None:
    response = web_client.get("/login")

    assert response.status_code == 200
    assert "Welcome back" in response.text
    assert "Code Agent" in response.text
    assert web_client.get("/static/css/code-agent.css").status_code == 200
    assert web_client.get("/static/js/web-ui.js").status_code == 200


@pytest.mark.parametrize("path", ["/", "/time-tracker"])
def test_protected_pages_redirect_anonymous_users(web_client: TestClient, path: str) -> None:
    response = web_client.get(path, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_requires_both_credentials(web_client: TestClient) -> None:
    response = web_client.post("/login", data={"username": "agent"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=missing"


def test_login_rejects_invalid_or_inactive_users(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(views, "authenticate_web_user", AsyncMock(return_value=None))

    response = web_client.post(
        "/login",
        data={"username": "inactive", "password": "not-used"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?error=invalid"
    assert "token" not in response.headers.get("set-cookie", "").lower()


def test_login_renders_dashboard_and_time_tracker_for_active_user(
    web_client: TestClient,
    test_app: CodeAgentAPP,
    active_user: MockUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(views, "authenticate_web_user", AsyncMock(return_value=active_user))
    monkeypatch.setattr(views, "get_current_web_user", AsyncMock(return_value=active_user))

    login_response = web_client.post(
        "/login",
        data={"username": "agent", "password": "secret"},
        follow_redirects=False,
    )
    dashboard_response = web_client.get("/")
    time_tracker_response = web_client.get("/time-tracker")

    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/"
    session_cookie = login_response.headers["set-cookie"]
    session_cookie_lower = session_cookie.lower()
    assert "code_agent_web_session" in session_cookie_lower
    assert "httponly" in session_cookie_lower
    assert "samesite=lax" in session_cookie_lower
    assert "secure" in session_cookie_lower
    assert "web_user_id" not in login_response.text
    assert "Dashboard" in dashboard_response.text
    assert "No work data yet" in dashboard_response.text
    assert "Version" in dashboard_response.text
    assert test_app.settings.app_version in dashboard_response.text
    assert "agent" in dashboard_response.text
    assert "nav-link is-active" in dashboard_response.text
    assert "Time Tracker" in time_tracker_response.text
    assert "No active timer" in time_tracker_response.text


def test_logout_clears_web_session(
    web_client: TestClient, active_user: MockUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(views, "authenticate_web_user", AsyncMock(return_value=active_user))
    web_client.post(
        "/login",
        data={"username": "agent", "password": "secret"},
        follow_redirects=False,
    )

    response = web_client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert "code_agent_web_session=null" in response.headers["set-cookie"]
