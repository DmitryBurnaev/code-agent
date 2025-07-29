"""Tests for system API endpoints."""

from datetime import datetime

from starlette.testclient import TestClient

from src.models import LLMVendor


class TestSystemAPI:
    """Tests for system API endpoints."""

    def test_get_system_info(self, client: TestClient, llm_vendors: list[LLMVendor]) -> None:
        """Test GET /system/info/ endpoint."""
        response = client.get("/api/system/info/")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "ok",
            "vendors": [vendor.slug for vendor in llm_vendors],
        }

    def test_health_check(self, client: TestClient) -> None:
        """Test GET /system/health/ endpoint."""
        response = client.get("/api/system/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert isinstance(datetime.fromisoformat(data["timestamp"]), datetime)
