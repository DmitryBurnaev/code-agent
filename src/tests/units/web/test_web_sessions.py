from unittest.mock import AsyncMock
from pathlib import Path
from base64 import b64encode

from itsdangerous import TimestampSigner

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

from src.db.models import User
from src.db.services import SASessionUOW
from src.main import CodeAgentAPP, make_app
from src.modules.admin.auth import AdminAuth
from src.modules.web import views
from src.modules.web.auth import SESSION_USER_ID
from src.settings import AppSettings
from src.settings.app import WebSettings


@pytest.fixture
def test_app(app_settings_test: AppSettings) -> CodeAgentAPP:
    # These session regressions need the real HTTP stack, but no database or lifespan.
    return make_app(app_settings_test)


def test_http_session_setting_is_loaded_from_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WEB_SESSION_HTTPS_ONLY", raising=False)
    (tmp_path / ".env").write_text(
        "WEB_SESSION_HTTPS_ONLY=false\nUNRELATED_SETTING=example\n", encoding="utf-8"
    )
    assert WebSettings().session_https_only is False
    monkeypatch.setenv("WEB_SESSION_HTTPS_ONLY", "true")
    assert WebSettings().session_https_only is True


def test_secure_cookie_on_http_loses_login_and_logs_reason(
    test_app: CodeAgentAPP, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    user = User(id=7, username="agent", is_active=True)
    monkeypatch.setattr(views, "authenticate_web_user", AsyncMock(return_value=user))
    client = TestClient(test_app, base_url="http://testserver")
    try:
        response = client.post(
            "/login",
            data={"username": "agent", "password": "private-test-password"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert client.get("/", follow_redirects=False).headers["location"] == "/login"
        assert "Login cookie is Secure on HTTP" in caplog.text
        assert "cookie_present=False" in caplog.text
        assert "missing_session_user_id" in caplog.text
        assert "private-test-password" not in caplog.text
    finally:
        client.close()


@pytest.mark.parametrize("reason", ["invalid_signature", "expired"])
def test_rejected_session_cookie_is_diagnosed(
    test_app: CodeAgentAPP,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    reason: str,
) -> None:
    cookie = "invalid-private-cookie"
    if reason == "expired":
        signer = TimestampSigner(test_app.settings.app_secret_key.get_secret_value())
        monkeypatch.setattr(signer, "get_timestamp", lambda: 1)
        cookie = signer.sign(b64encode(b'{"web_user_id":7}')).decode()
    client = TestClient(test_app, base_url="https://testserver")
    try:
        client.cookies.set(test_app.settings.web.session_cookie_name, cookie)
        assert client.get("/", follow_redirects=False).headers["location"] == "/login"
        assert f"Cookie rejected: reason={reason}" in caplog.text
        assert "cookie_present=True" in caplog.text
        assert cookie not in caplog.text
        assert test_app.settings.app_secret_key.get_secret_value() not in caplog.text
    finally:
        client.close()


@pytest.mark.parametrize("admin_path", ["/cadm", "/custom/admin"])
@pytest.mark.parametrize("scheme,https_only", [("https", True), ("http", False)])
@pytest.mark.parametrize("root_path", ["", "/prefix"])
def test_admin_requests_preserve_web_login(
    test_app: CodeAgentAPP,
    monkeypatch: pytest.MonkeyPatch,
    admin_path: str,
    scheme: str,
    https_only: bool,
    root_path: str,
) -> None:
    test_app.settings.admin.base_url = admin_path
    middleware = test_app.user_middleware[0]
    middleware.kwargs["admin_path"] = admin_path
    middleware.kwargs["https_only"] = https_only
    user = User(id=7, username="agent", is_active=True, is_admin=True)
    monkeypatch.setattr(views, "authenticate_web_user", AsyncMock(return_value=user))
    monkeypatch.setattr("src.modules.web.auth.UserRepository.first", AsyncMock(return_value=user))
    uow = AsyncMock(spec=SASessionUOW)
    uow.__aenter__.return_value = uow
    monkeypatch.setattr("src.modules.web.auth.SASessionUOW", lambda: uow)

    async def admin_login(request: Request) -> Response:
        request.session.update({"token": "admin-token"})
        return Response()

    async def admin_logout(request: Request) -> Response:
        request.session.clear()
        return Response()

    async def web_session(request: Request) -> Response:
        return Response(str(request.session.get(SESSION_USER_ID)))

    async def admin_session(request: Request) -> Response:
        return Response(str(request.session.get("token")))

    backend = AdminAuth("test-admin-secret", test_app.settings)
    test_app.mount(
        admin_path,
        Starlette(
            routes=[
                Route("/login", admin_login),
                Route("/logout", admin_logout),
                Route("/session", admin_session),
            ],
            middleware=backend.middlewares,
        ),
    )
    test_app.add_route(admin_path + "-web", web_session)
    # No lifespan: this test exercises HTTP sessions with mocked persistence.
    client = TestClient(test_app, base_url=f"{scheme}://testserver{root_path}", root_path=root_path)
    try:
        response = client.post(
            "/login", data={"username": "agent", "password": "secret"}, follow_redirects=False
        )
        assert response.status_code == 303
        assert ("; secure" in response.headers["set-cookie"]) is https_only
        assert client.get("/login", follow_redirects=False).headers["location"] == "/"
        assert client.get(admin_path + "-web").text == "7"

        for path in ("/login", "/logout"):
            response = client.get(admin_path + path)
            assert response.status_code == 200
            assert "code_agent_web_session" not in response.headers.get("set-cookie", "")
            response = client.get("/login", follow_redirects=False)
            assert response.status_code == 303
            assert response.headers["location"] == "/"

        client.get(admin_path + "/login")
        client.post("/logout")
        assert client.get("/login").status_code == 200
        assert client.get(admin_path + "-web").text == "None"
        assert client.get(admin_path + "/session").text == "admin-token"
    finally:
        client.close()
