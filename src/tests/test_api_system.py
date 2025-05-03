"""Tests for system API endpoints."""

from datetime import datetime
from typing import Any, Generator
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from starlette.testclient import TestClient

from src.models import LLMProvider

pytestmark = pytest.mark.asyncio


class TestSystemAPI:
    """Tests for system API endpoints."""

    def test_get_system_info(self, client: TestClient, providers: list[LLMProvider]) -> None:
        """Test GET /system/info/ endpoint."""
        response = client.get("/api/system/info/")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "ok",
            "providers": [provider.vendor for provider in providers],
        }

    def test_health_check(self, client: TestClient) -> None:
        """Test GET /system/health/ endpoint."""
        response = client.get("/api/system/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert isinstance(datetime.fromisoformat(data["timestamp"]), datetime)
