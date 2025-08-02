"""Tests for system API endpoints."""

from datetime import datetime

from starlette.testclient import TestClient

from src.models import LLMVendor
from src.tests.conftest import MockVendor


class TestSystemAPI:
    """Tests for system API endpoints."""

    def test_get_system_info(self, client: TestClient, mock_db_vendors: list[MockVendor]) -> None:
        """Test GET /system/info/ endpoint."""
        response = client.get("/api/system/info/")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "ok",
            "vendors": [vendor.slug for vendor in mock_db_vendors],
        }

    def test_health_check(self, client: TestClient) -> None:
        """Test GET /system/health/ endpoint."""
        response = client.get("/api/system/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert isinstance(datetime.fromisoformat(data["timestamp"]), datetime)
