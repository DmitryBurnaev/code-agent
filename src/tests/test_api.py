import platform

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.dependencies.settings import get_app_settings
from src.main import make_app
from src.settings import AppSettings, LLMProvider


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
    return [LLMProvider(api_provider="test-provider", api_key=SecretStr("test-api-key"))]


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
        "providers": ["test-provider"],
    }
