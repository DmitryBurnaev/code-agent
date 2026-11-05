"""Regressions for the security findings tracked in issue #56."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.testclient import TestClient

from src.application import CodeAgentAPP
from src.db.models import Token, User
from src.db.repositories import TokenRepository, UserRepository
from src.main import make_app
from src.modules.admin.app import make_admin
from src.modules.auth.tokens import (
    authenticate_api_token,
    decode_api_token,
    hash_token,
    make_api_token,
)
from src.modules.web import views
from src.settings import AppSettings
from src.utils import admin_get_link


@pytest.fixture
def test_app(app_settings_test: AppSettings, monkeypatch: pytest.MonkeyPatch) -> CodeAgentAPP:
    # Real middleware and routes; no lifespan or database connection is needed.
    factory = async_sessionmaker[AsyncSession]()
    monkeypatch.setattr("src.db.session.get_session_factory", lambda: factory)
    app = make_app(app_settings_test)
    make_admin(app)
    return app


MUTATIONS = (
    ("POST", "/login"),
    ("POST", "/logout"),
    ("POST", "/time-tracker/timer/start"),
    ("POST", "/time-tracker/timer/stop"),
    ("POST", "/time-tracker/entries"),
    ("POST", "/time-tracker/entries/1"),
    ("POST", "/time-tracker/entries/1/delete"),
    ("POST", "/cadm/login"),
    ("GET", "/cadm/logout"),
    ("POST", "/cadm/user/create"),
    ("POST", "/cadm/user/edit/1"),
    ("DELETE", "/cadm/user/delete?pks=1"),
    ("POST", "/cadm/toggl-import"),
    ("GET", "/cadm/token/action/activate?pks=1"),
    ("GET", "/cadm/token/action/deactivate?pks=1"),
)


@pytest.mark.parametrize("method,path", MUTATIONS)
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://attacker.test"},
        {"Origin": "null", "Referer": "https://testserver/login"},
        {"Origin": "https://testserver.attacker.test"},
        {"Referer": "https://attacker.test/form"},
        {"Origin": "http://testserver"},
        {"Origin": "https://testserver:8443"},
        {"Origin": "https://testserver:0"},
        {"Origin": "https://testserver", "Sec-Fetch-Site": "cross-site"},
        {"Origin": "https://[invalid"},
    ],
)
def test_forged_browser_mutations_fail_before_handlers(
    test_app: CodeAgentAPP,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    headers: dict[str, str],
) -> None:
    lookup = AsyncMock()
    monkeypatch.setattr(UserRepository, "get_by_username", lookup)
    client = TestClient(test_app, base_url="https://testserver")
    try:
        response = client.request(method, path, headers=headers, follow_redirects=False)
        assert response.status_code == 403
        assert response.text == "CSRF verification failed"
        lookup.assert_not_awaited()
    finally:
        client.close()


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://testserver"},
        {"Origin": "https://testserver:443"},
        {"Referer": "https://testserver/login?next=/"},
    ],
)
def test_same_origin_login_reaches_authentication(
    test_app: CodeAgentAPP, monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
) -> None:
    authenticate = AsyncMock(return_value=None)
    monkeypatch.setattr(views, "authenticate_web_user", authenticate)
    client = TestClient(test_app, base_url="https://testserver")
    try:
        response = client.post(
            "/login",
            data={"username": "agent", "password": "test-password"},
            headers=headers,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/login?error=invalid"
        authenticate.assert_awaited_once_with(username="agent", password="test-password")
    finally:
        client.close()


def test_api_authentication_does_not_require_browser_headers(test_app: CodeAgentAPP) -> None:
    client = TestClient(test_app, base_url="https://testserver")
    try:
        response = client.post("/api/ai-proxy/chat/completions", json={})
        assert response.status_code == 401
        assert "CSRF" not in response.text
        assert client.get("/login").status_code == 200
        assert client.get("/cadm/login").status_code == 200
    finally:
        client.close()


def test_admin_links_escape_stored_names_and_attributes(app_settings_test: AppSettings) -> None:
    user = User(id=7, username='<img src=x onerror="alert(1)">')
    link = admin_get_link(user, url_name='user" onclick="alert(2)')
    assert '<a href="/cadm/user&#34; onclick=&#34;alert(2)/edit/7">' in link
    assert "&lt;img" in link
    assert "<img" not in link
    assert ' onclick="' not in link


async def test_token_generation_decoding_and_rejection_do_not_log_credentials(
    app_settings_test: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    generated = make_api_token(expires_at=None, settings=app_settings_test)
    payload = decode_api_token(generated.value, app_settings_test)
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(TokenRepository, "get_by_token", lookup)
    request = Request({"type": "http", "method": "GET", "headers": []})
    with pytest.raises(HTTPException, match="unknown token"):
        await authenticate_api_token(request, app_settings_test, f"Bearer {generated.value}")
    lookup.assert_awaited_once_with(hash_token(payload.sub))
    signature_length = int(generated.value[-3:])
    signature = generated.value[-3 - signature_length : -3]
    assert generated.value not in caplog.text
    assert signature not in caplog.text
    assert payload.sub not in caplog.text
    assert generated.hashed_value not in caplog.text
    assert app_settings_test.app_secret_key.get_secret_value() not in caplog.text


async def test_repository_does_not_log_credential_values(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.fetchall.return_value = []
    session.execute.return_value = result
    repository = TokenRepository(session)
    value = "synthetic-private-credential"
    await repository.create({"token": value, "user_id": 7, "name": "test"})
    assert await repository.get_by_token(value) is None
    session.add.assert_called_once()
    assert isinstance(session.add.call_args.args[0], Token)
    assert value not in caplog.text
