from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.main import app
from app.settings import AppSettings


@pytest.fixture
def client() -> TestClient:
    """Create a test client with mocked settings."""
    mock_settings = MagicMock(spec=AppSettings)
    mock_settings.auth_api_token = SecretStr("test-token")
    mock_settings.docs_enabled = False
    mock_settings.app_host = "0.0.0.0"
    mock_settings.app_port = 8000
    mock_settings.log_level = "INFO"
    mock_settings.providers = []

    with patch("app.settings.app_settings", mock_settings):
        return TestClient(app)


def test_health_check(client: TestClient) -> None:
    """Test the health check endpoint."""
    response = client.get("/api/system/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    # Verify timestamp is in ISO format
    datetime.fromisoformat(data["timestamp"])


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


def test_system_info_authorized(client: TestClient) -> None:
    """Test system info endpoint with valid authorization."""
    mock_settings = MagicMock(spec=AppSettings)
    mock_settings.auth_api_token = SecretStr("test-token")
    mock_settings.docs_enabled = False
    mock_settings.app_host = "0.0.0.0"
    mock_settings.app_port = 8000
    mock_settings.log_level = "INFO"
    mock_settings.providers = []

    with patch("app.settings.app_settings", mock_settings):
        client = TestClient(app)
        response = client.get(
            "/api/system/info/",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_time" in data
        assert "os_version" in data
        # Verify current_time is in ISO format
        datetime.fromisoformat(data["current_time"])


@pytest.fixture
def client_with_docs() -> TestClient:
    """Create a test client with docs enabled."""
    mock_settings = MagicMock(spec=AppSettings)
    mock_settings.auth_api_token = SecretStr("test-token")
    mock_settings.docs_enabled = True
    mock_settings.app_host = "0.0.0.0"
    mock_settings.app_port = 8000
    mock_settings.log_level = "INFO"
    mock_settings.providers = []

    with patch("app.settings.app_settings", mock_settings):
        return TestClient(app)


def test_docs_disabled(client: TestClient) -> None:
    """Test that docs are disabled when configured."""
    response = client.get("/api/docs/")
    assert response.status_code == 404
    response = client.get("/api/redoc/")
    assert response.status_code == 404


def test_docs_enabled(client_with_docs: TestClient) -> None:
    """Test that docs are enabled when configured."""
    response = client_with_docs.get("/api/docs/")
    assert response.status_code == 200
    response = client_with_docs.get("/api/redoc/")
    assert response.status_code == 200
