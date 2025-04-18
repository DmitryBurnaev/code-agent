import platform
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Request, Response
from pydantic import SecretStr

from src.dependencies.settings import get_app_settings
from src.main import make_app
from src.settings import AppSettings, LLMProvider, Provider, PROVIDER_URLS


@pytest.fixture
def auth_test_token() -> str:
    return "test-auth-token"


@pytest.fixture
def auth_test_header(auth_test_token) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {auth_test_token}",
    }


@pytest.fixture
def providers() -> list[LLMProvider]:
    return [
        LLMProvider(
            api_provider=Provider.OPENAI,
            api_key=SecretStr("test-key"),
        )
    ]


@pytest.fixture
def client(auth_test_token, providers) -> TestClient:
    """Create a test client with mocked settings."""
    test_settings = AppSettings(
        auth_api_token=SecretStr(auth_test_token),
        providers=providers,
    )
    test_app = make_app(settings=test_settings)
    test_app.dependency_overrides = {
        get_app_settings: lambda: test_settings,
    }
    return TestClient(test_app)


def test_health_check(client: TestClient, auth_test_header: dict[str, str]) -> None:
    """Test the health check endpoint."""
    response = client.get("/api/system/health/", headers=auth_test_header)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_system_info_unauthorized(client: TestClient) -> None:
    """Test system info endpoint without authorization."""
    response = client.get("/api/system/info/")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_system_info_invalid_token(client: TestClient) -> None:
    """Test system info endpoint with invalid token."""
    response = client.get(
        "/api/system/info/",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid authentication token"


def test_system_info_authorized(client: TestClient, auth_test_header: dict[str, str]) -> None:
    """Test system info endpoint with valid authorization."""
    response = client.get("/api/system/info/", headers=auth_test_header)
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "status": "ok",
        "os_version": platform.platform(),
        "providers": ["openai"],
    }


def test_proxy_route_not_found(client: TestClient, auth_test_header: dict[str, str]) -> None:
    """Test proxy route with non-existent provider."""
    response = client.get("/api/proxy/non-existent/test", headers=auth_test_header)
    assert response.status_code == 404
    assert response.json()["detail"] == "No matching proxy route found"


def test_proxy_route_unauthorized(client: TestClient) -> None:
    """Test proxy route without authorization."""
    response = client.get("/api/proxy/openai/models")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_proxy_route_success(
    client: TestClient,
    auth_test_header: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test successful proxy request."""

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock successful response from provider."""
        assert kwargs["url"] == f"{PROVIDER_URLS[Provider.OPENAI]}/models"
        assert kwargs["headers"].get("Authorization") == auth_test_header["Authorization"]
        return Response(200, json={"models": ["gpt-4", "gpt-3.5-turbo"]})

    # Патчим httpx.AsyncClient.request чтобы не делать реальных запросов
    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    response = client.get("/api/proxy/openai/models", headers=auth_test_header)
    assert response.status_code == 200
    data = response.json()
    assert data == {"models": ["gpt-4", "gpt-3.5-turbo"]}


def test_proxy_route_provider_error(
    client: TestClient,
    auth_test_header: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test proxy request when provider returns error."""

    def mock_request(self: Request, **kwargs: Any) -> Response:
        """Mock error response from provider."""
        return Response(
            429,
            json={"error": {"message": "Rate limit exceeded"}},
        )

    monkeypatch.setattr("httpx.AsyncClient.request", mock_request)

    response = client.get("/api/proxy/openai/chat/completions", headers=auth_test_header)
    assert response.status_code == 429
    data = response.json()
    assert data == {"error": {"message": "Rate limit exceeded"}}
