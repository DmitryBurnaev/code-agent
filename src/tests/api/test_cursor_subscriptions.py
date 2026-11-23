"""Subscription authorization and checkout through real code-agent HTTP routes."""

from collections.abc import Generator
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.testclient import TestClient

from src.application import CodeAgentAPP
from src.constants import VendorMode
from src.db.models import Token, User, Vendor
from src.db.repositories import TokenRepository, UserRepository, VendorRepository
from src.modules.auth.tokens import GeneratedToken, make_api_token
from agents.protocol import CursorErrorCode
from src.services.cursor import CursorClient, CursorError
from src.settings import AppSettings

API_PATH = "/api/ai-proxy"
CHAT = {"model": "cursor:fixture", "messages": [{"role": "user", "content": "fixture prompt"}]}


@pytest.fixture
def cursor_vendor(monkeypatch: pytest.MonkeyPatch) -> Vendor:
    vendor = Vendor(
        id=1,
        slug="cursor",
        auth_mode=VendorMode.SUBSCRIPTION,
        is_active=True,
        subscription_models=["fixture", "missing"],
    )
    monkeypatch.setattr(VendorRepository, "get_by_slug", AsyncMock(return_value=vendor))
    monkeypatch.setattr(VendorRepository, "filter", AsyncMock(return_value=[vendor]))
    return vendor


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/models":
            return httpx.Response(200, json={"models": ["fixture", "auto"]})
        if request.url.path == "/auth/status":
            return httpx.Response(200, json={"state": "logged_in"})
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"url": "https://cursor.com/login?challenge=fixture"})
        if request.url.path == "/run":
            payload = json.loads(request.content)
            terminal = (
                '{"type":"error","code":"subscription_usage_limit"}'
                if payload["messages"][-1]["content"] == "quota"
                else '{"type":"done"}'
            )
            return httpx.Response(
                200,
                text='{"type":"delta","text":"hello"}\n' + terminal + "\n",
                headers={"content-type": "application/x-ndjson"},
            )
        raise AssertionError(f"Unexpected upstream path {request.url.path}")

    def http(_client: CursorClient) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://agents")

    monkeypatch.setattr(CursorClient, "_http", http)
    return requests


@pytest.fixture
def accounts(
    app_settings_test: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[User, Token, GeneratedToken]]:
    result = []
    for user_id in (1, 2):
        user = User(
            id=user_id,
            username=f"test-user-{user_id}",
            password=User.make_password("test"),
            is_active=True,
            is_admin=False,
            can_access_admin=user_id == 1,
            can_use_llm=True,
            can_use_ai_subscriptions=False,
        )
        credentials = make_api_token(expires_at=None, settings=app_settings_test)
        token = Token(id=user_id, user=user, token=credentials.hashed_value, is_active=True)
        result.append((user, token, credentials))
    monkeypatch.setattr(
        TokenRepository,
        "get_by_token",
        AsyncMock(side_effect={token.token: token for _, token, _ in result}.get),
    )
    monkeypatch.setattr(UserRepository, "get_by_username", AsyncMock(return_value=result[0][0]))
    monkeypatch.setattr(UserRepository, "first", AsyncMock(return_value=result[0][0]))
    return result


@pytest.fixture
def public_client(test_app: CodeAgentAPP) -> Generator[TestClient]:
    with TestClient(test_app, base_url="https://testserver") as client:
        yield client


def test_catalog_and_chat_recheck_every_token(
    public_client: TestClient,
    cursor_vendor: Vendor,
    upstream: list[httpx.Request],
    accounts: list[tuple[User, Token, GeneratedToken]],
) -> None:
    for user, token, credentials in accounts:
        public_client.headers["Authorization"] = f"Bearer {credentials.value}"
        previous_requests = len(upstream)
        assert public_client.get(f"{API_PATH}/models").json() == {"data": []}
        denied = public_client.post(f"{API_PATH}/chat/completions", json=CHAT)
        assert denied.status_code == 403
        assert len(upstream) == previous_requests

        user.can_use_ai_subscriptions = True
        assert public_client.get(f"{API_PATH}/models").json()["data"] == [
            {"id": "cursor:fixture", "vendor": "cursor", "vendor_id": "fixture"}
        ]
        response = public_client.post(f"{API_PATH}/chat/completions", json=CHAT)
        assert response.status_code == 200
        assert response.json()["model"] == "cursor:fixture"
        assert response.json()["choices"][0]["message"]["content"] == "hello"

        user.can_use_ai_subscriptions = False
        assert public_client.post(f"{API_PATH}/chat/completions", json=CHAT).status_code == 403
        user.is_admin = True
        assert public_client.post(f"{API_PATH}/chat/completions", json=CHAT).status_code == 200
        token.is_active = False
        assert public_client.post(f"{API_PATH}/chat/completions", json=CHAT).status_code == 401


def test_chat_requires_enabled_available_model_and_text_parameters(
    public_client: TestClient,
    cursor_vendor: Vendor,
    upstream: list[httpx.Request],
    accounts: list[tuple[User, Token, GeneratedToken]],
) -> None:
    user, _, credentials = accounts[0]
    user.can_use_ai_subscriptions = True
    public_client.headers["Authorization"] = f"Bearer {credentials.value}"
    endpoint = f"{API_PATH}/chat/completions"
    assert public_client.post(endpoint, json=CHAT | {"model": "cursor:auto"}).status_code == 404
    assert not upstream
    assert public_client.post(endpoint, json=CHAT | {"model": "cursor:missing"}).status_code == 404
    assert [request.url.path for request in upstream] == ["/models"]
    assert public_client.post(endpoint, json=CHAT | {"tools": []}).status_code == 400
    cursor_vendor.subscription_models = ["auto"]
    assert public_client.post(endpoint, json=CHAT | {"model": "cursor:fixture"}).status_code == 404
    # The explicit Auto ID passes through unchanged when the admin enables it.
    assert public_client.post(endpoint, json=CHAT | {"model": "cursor:auto"}).status_code == 200
    assert json.loads(upstream[-1].content)["model"] == "auto"

    cursor_vendor.subscription_models = ["fixture"]
    stream = public_client.post(endpoint, json=CHAT | {"stream": True})
    assert stream.status_code == 200
    assert stream.headers["x-accel-buffering"] == "no"
    assert '"content": "hello"' in stream.text
    assert "data: [DONE]" in stream.text
    quota = {"messages": [{"role": "user", "content": "quota"}]}
    stream_error = public_client.post(endpoint, json=CHAT | quota | {"stream": True})
    assert "subscription_usage_limit" in stream_error.text
    assert "[DONE]" not in stream_error.text
    assert public_client.post(endpoint, json=CHAT | quota).status_code == 429


def test_openai_cannot_use_subscription_even_with_invalid_stored_mode(
    public_client: TestClient,
    cursor_vendor: Vendor,
    upstream: list[httpx.Request],
    accounts: list[tuple[User, Token, GeneratedToken]],
) -> None:
    user, _, credentials = accounts[0]
    user.can_use_ai_subscriptions = True
    cursor_vendor.slug = "openai"
    public_client.headers["Authorization"] = f"Bearer {credentials.value}"
    response = public_client.post(
        f"{API_PATH}/chat/completions", json=CHAT | {"model": "openai:gpt"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_vendor_mode"
    assert not upstream


async def test_cursor_reports_missing_agent_secret(app_settings_test: AppSettings) -> None:
    settings = app_settings_test.model_copy(update={"cursor_agents_secret": None})
    with pytest.raises(CursorError) as error:
        await CursorClient(settings).status()
    assert error.value.code == CursorErrorCode.NOT_CONFIGURED
    assert error.value.status == 503


@pytest.mark.parametrize("status_code", [401, 403])
async def test_cursor_reports_agent_auth_failure(
    app_settings_test: AppSettings, monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    def http(_client: CursorClient) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(status_code)),
            base_url="http://agents",
        )

    monkeypatch.setattr(CursorClient, "_http", http)
    with pytest.raises(CursorError) as error:
        await CursorClient(app_settings_test).status()
    assert error.value.code == CursorErrorCode.AUTH_FAILED
    assert error.value.status == 503


def test_admin_subscription_view_and_openai_form(
    public_client: TestClient,
    cursor_vendor: Vendor,
    upstream: list[httpx.Request],
    accounts: list[tuple[User, Token, GeneratedToken]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = accounts[0][0]
    assert (
        public_client.post(
            "/cadm/login",
            data={"username": user.username, "password": "test"},
            headers={"Origin": "https://testserver"},
            follow_redirects=False,
        ).status_code
        == 302
    )
    panel = "/cadm/vendor/cursor-subscription"
    page = public_client.get(panel)
    assert page.status_code == 200
    assert page.headers["Referrer-Policy"] == "same-origin"
    assert "Subscription models" in page.text
    assert "missing (Unavailable)" in page.text
    assert public_client.post(panel, data={"action": "refresh"}).status_code == 403
    assert (
        public_client.post(panel, data={"action": "login"}, headers={"Origin": "null"}).status_code
        == 403
    )
    connected = public_client.post(
        panel,
        data={"action": "login"},
        headers={"Referer": f"https://testserver{panel}"},
    )
    assert connected.status_code == 200
    assert "https://cursor.com/login?challenge=fixture" in connected.text
    assert 'rel="noopener noreferrer"' in connected.text
    fake_save = AsyncMock()
    monkeypatch.setattr(
        "src.modules.admin.views.vendors.VendorAdminView._save_subscription_models", fake_save
    )
    saved = public_client.post(
        panel,
        data={"action": "save", "models": ["fixture", "auto"]},
        headers={"Origin": "https://testserver"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    fake_save.assert_awaited_once_with(["fixture", "auto"], {"fixture", "auto"})

    monkeypatch.setattr(VendorRepository, "filter", AsyncMock(return_value=[]))
    refused = public_client.post(
        "/cadm/vendor/create",
        data={
            "slug": "openai",
            "auth_mode": "subscription",
            "api_url": "https://api.openai.com/v1",
        },
        headers={"Origin": "https://testserver"},
    )
    assert refused.status_code == 400
    assert "Subscription is only supported for Cursor" in refused.text
