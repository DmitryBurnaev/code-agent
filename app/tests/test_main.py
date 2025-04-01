from datetime import datetime
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client with mocked settings."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.API_TOKEN = "test-token"
        mock_settings.SERVICE_TOKENS = {"service1": "token1"}
        mock_settings.ENABLE_SWAGGER = False
        return TestClient(app)


def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_system_info_unauthorized(client):
    """Test system info endpoint without authorization."""
    response = client.get("/system-info")
    assert response.status_code == 401


def test_system_info_authorized(client):
    """Test system info endpoint with authorization."""
    response = client.get(
        "/system-info",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "current_time" in data
    assert "os_version" in data 