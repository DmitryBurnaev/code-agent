from datetime import datetime

from starlette.testclient import TestClient

from src.tests.mocks import MockVendor


class TestSystemAPI:

    def test_get_system_info(
        self, client: TestClient, mock_db_vendors__all: list[MockVendor]
    ) -> None:
        response = client.get("/api/system/info/")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "ok",
            "vendors": [vendor.slug for vendor in mock_db_vendors__all],
        }

    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/api/system/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert isinstance(datetime.fromisoformat(data["timestamp"]), datetime)
